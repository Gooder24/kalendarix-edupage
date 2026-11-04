import argparse
import logging
import sys
import time
from datetime import datetime

import uvicorn

from kalendarix_edupage import edupage_client
from kalendarix_edupage.api import create_app
from kalendarix_edupage.config import Settings, get_settings
from kalendarix_edupage.store import Store
from kalendarix_edupage.sync import run_sync

TWO_FACTOR_TIMEOUT = 120


def _confirm_two_factor(two_factor) -> None:
    print(
        "  Účet má dvojfaktorové overenie – potvrď prihlásenie v mobilnej "
        f"aplikácii EduPage (čakám {TWO_FACTOR_TIMEOUT} s)…",
        flush=True,
    )
    deadline = time.monotonic() + TWO_FACTOR_TIMEOUT
    while not two_factor.is_confirmed():
        if time.monotonic() > deadline:
            raise edupage_client.EdupageLoginError(
                "Druhý faktor nebol potvrdený včas."
            )
        time.sleep(2)
    two_factor.finish()


def verify_login(settings: Settings, attempts: int, pause: float) -> int:
    """Log in several times in a row to prove unattended login is reliable."""
    today = datetime.now(settings.tz).date()
    succeeded = 0
    edupage = None

    for n in range(1, attempts + 1):
        if n > 1:
            time.sleep(pause)
        started = time.monotonic()
        try:
            edupage, two_factor = edupage_client.fresh_login(settings)
            if two_factor is not None:
                _confirm_two_factor(two_factor)
            lessons = edupage_client.fetch_day(edupage, today)
        except edupage_client.EdupageLoginError as exc:
            print(f"[{n}/{attempts}] ZLYHALO: {exc}")
            # Wrong password or captcha: repeating only makes a lockout likelier.
            break
        except Exception as exc:
            print(f"[{n}/{attempts}] ZLYHALO: {type(exc).__name__}: {exc}")
            continue

        succeeded += 1
        print(
            f"[{n}/{attempts}] OK za {time.monotonic() - started:.1f} s – "
            f"{edupage.get_user_id()} @ {edupage.subdomain}, "
            f"dnes {len(lessons)} záznamov v rozvrhu"
        )
        if n < attempts:
            edupage.logout()  # do not leave a pile of open sessions behind

    # Keep the last session: this is what the backend reuses after a restart.
    reusable = False
    if edupage is not None and edupage.is_logged_in:
        reusable = (
            edupage_client.save_session(settings, edupage)
            and edupage_client.restore_session(settings) is not None
        )
        print(f"Opätovné použitie uloženej relácie: {'OK' if reusable else 'ZLYHALO'}")

    print(f"VÝSLEDOK: {succeeded}/{attempts} prihlásení úspešných")
    return 0 if succeeded == attempts and reusable else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="kalendarix-edupage")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="spustí API server a pravidelnú synchronizáciu")
    commands.add_parser("sync", help="jednorazovo stiahne rozvrh z EduPage")
    verify = commands.add_parser(
        "verify-login", help="niekoľkokrát overí prihlásenie do EduPage"
    )
    verify.add_argument("--attempts", type=int, default=3)
    verify.add_argument("--pause", type=float, default=5.0, help="sekundy medzi pokusmi")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    if args.command == "verify-login":
        sys.exit(verify_login(settings, args.attempts, args.pause))

    if args.command == "sync":
        status = run_sync(settings, Store(settings.kx_data_dir))
        print(status)
        sys.exit(0 if status["ok"] else 1)

    uvicorn.run(create_app(settings), host=settings.kx_host, port=settings.kx_port)
