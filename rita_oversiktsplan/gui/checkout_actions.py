"""Checka ut och checka in en databasplan: frågorna och flödet runt ``core.checkout`` (som i Rita Detaljplan).

Alla frågor till användaren går via ``ask_*``-metoderna, så att de kan bytas ut i tester."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

from ..core import checkout as co
from ..core.storage import PostgisError

CHECK_IN, DISCARD, CANCEL = "in", "discard", "cancel"


class CheckoutActions:
    def __init__(self, report: Callable[[str, bool], None], parent=None,
                 after: Optional[Callable[[], None]] = None):
        self.report = report  # (text, är_varning)
        self.parent = parent
        self.after = after or (lambda: None)

    # -- frågor (byts ut i tester) ---------------------------------------------------------------------------------
    def ask_yes_no(self, title: str, text: str, yes: str = "Ja", no: str = "Avbryt") -> bool:
        box = QMessageBox(self.parent)
        box.setWindowTitle(title)
        box.setText(text)
        yes_button = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(no, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is yes_button

    def ask_break_lock(self, lock: Optional[co.Lock]) -> bool:
        """Planen är utcheckad av någon annan. Returnerar True om låset ska brytas."""
        who = lock.describe() if lock is not None else "någon annan"
        box = QMessageBox(self.parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Planen är utcheckad")
        box.setText(f"Planen är utcheckad av {who}.")
        box.setInformativeText("Bara en kan redigera planen åt gången. Vänta tills den har checkats in, eller bryt "
                               "låset om utcheckningen är övergiven. Bryter du låset kan den andra inte längre "
                               "checka in sina ändringar.")
        box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        breaking = box.addButton("Bryt låset…", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        if box.clickedButton() is not breaking:
            return False
        return self.ask_yes_no("Bryt låset", f"Vill du bryta låset som tillhör {who}? Deras ändringar som inte har "
                                             "checkats in går inte att lämna in efteråt.", "Bryt låset")

    def ask_check_in(self) -> str:
        box = QMessageBox(self.parent)
        box.setWindowTitle("Checka in planen")
        box.setText("Vad vill du göra med den utcheckade planen?")
        box.setInformativeText("Checka in skriver planen till databasen och släpper låset. Kasta utcheckningen släpper "
                               "låset utan att spara något: ändringarna i den lokala kopian går förlorade.")
        do_in = box.addButton("Checka in", QMessageBox.ButtonRole.AcceptRole)
        do_discard = box.addButton("Kasta utcheckningen…", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Avbryt", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        return CHECK_IN if clicked is do_in else DISCARD if clicked is do_discard else CANCEL

    # -- flöden ----------------------------------------------------------------------------------------------------
    @staticmethod
    def _busy():
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

    @staticmethod
    def _idle():
        QApplication.restoreOverrideCursor()

    def check_out(self, group, ask: bool = True) -> bool:
        """Checkar ut planen för redigering (eller tar upp en tidigare utcheckning). True om planen nu är utcheckad."""
        state = co.state(group)
        if state == co.LOCAL:
            return True
        if state != co.DATABASE:
            self.report("Planen ligger i en fil och behöver inte checkas ut.", False)
            return False
        if co.is_editing(group):
            self.report("Avsluta redigeringen först.", True)
            return False
        plan = co.db_storage(group)
        try:
            previous = co.resumable_copy(plan)
        except PostgisError as exc:
            self.report(f"Kunde inte läsa planens lås i databasen: {exc}", True)
            return False
        if previous is not None:
            path, lock = previous
            if not self.ask_yes_no("Fortsätt utcheckningen", "Du har redan checkat ut planen på den här datorn "
                                   f"({lock.since.replace('T', ' ')}). Vill du fortsätta redigera den kopian?",
                                   "Fortsätt"):
                return False
            try:
                co.resume(group, path, lock)
            except co.CheckoutError as exc:
                self.report(str(exc), True)
                return False
            self.report("Fortsätter med din utcheckade kopia. Checka in planen när du är klar.", False)
            self.after()
            return True
        if ask and not self.ask_yes_no(
                "Checka ut planen", "Planen ligger i databasen och är skrivskyddad. Checkar du ut den låses den för "
                "andra och en lokal kopia skapas som du redigerar. När du är klar checkar du in planen igen.",
                "Checka ut"):
            return False
        return self._do_check_out(group, retry=True)

    def _do_check_out(self, group, retry: bool) -> bool:
        self._busy()
        try:
            path = co.check_out(group)
        except co.LockedError as exc:
            self._idle()
            if retry and self.ask_break_lock(exc.lock):
                try:
                    co.break_lock(co.db_storage(group))
                except PostgisError as inner:
                    self.report(f"Kunde inte bryta låset: {inner}", True)
                    return False
                return self._do_check_out(group, retry=False)
            return False
        except co.CheckoutError as exc:
            self._idle()
            self.report(str(exc), True)
            return False
        self._idle()
        self.report(f"Checkade ut planen till en lokal kopia ({path.name}). Checka in den när du är klar.", False)
        self.after()
        return True

    def check_in(self, group) -> bool:
        """Checkar in planen (eller kastar utcheckningen). True om planen är tillbaka i databasen."""
        if co.state(group) != co.LOCAL:
            self.report("Planen är inte utcheckad.", True)
            return False
        if co.is_editing(group):
            self.report("Avsluta redigeringen först (spara eller kasta ändringarna).", True)
            return False
        choice = self.ask_check_in()
        if choice == CANCEL:
            return False
        if choice == DISCARD:
            if not self.ask_yes_no("Kasta utcheckningen", "Ändringarna i den lokala kopian tas bort och går inte att "
                                   "få tillbaka. Vill du kasta utcheckningen?", "Kasta"):
                return False
            return self._finish(group, co.discard, "Kastade utcheckningen. Planen är oförändrad i databasen.")
        return self._finish(group, co.check_in, "Checkade in planen i databasen.")

    def _finish(self, group, action, done_text: str) -> bool:
        self._busy()
        try:
            path, removed = action(group)
        except co.CheckoutError as exc:
            self.report(str(exc) + " Din lokala kopia och låset är kvar.", True)
            return False
        finally:
            self._idle()
        self.report(done_text + ("" if removed else f" Den lokala kopian {path} kunde inte tas bort: ta bort den för "
                                                    "hand."), not removed)
        self.after()
        return True
