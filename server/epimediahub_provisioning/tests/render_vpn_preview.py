"""Browser QA against a local, disposable dashboard. Never connects to real users."""
import os
from pathlib import Path
import shutil
import sys
import threading

from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_vpn_dashboard import DashboardTests, core


def main():
    fixture=DashboardTests();fixture.setUp()
    fixture.bind();fixture.fund();fixture.post("grant",device_row_id=1,days=7);fixture.ack()
    with core.db() as con:
        con.execute("UPDATE resellers SET password_hash=? WHERE id=1",(generate_password_hash("preview-reseller-password"),))
        con.execute("UPDATE customers SET name='Vorschau · Familie Nord' WHERE id=1")
        con.execute("UPDATE customers SET name='Vorschau · Familie Süd' WHERE id=2")
    server=make_server("127.0.0.1",0,core.app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f"http://127.0.0.1:{server.server_port}"
    output=Path(os.environ.get("VPN_PREVIEW_DIR","/tmp/epimediahub-vpn-preview"));output.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=os.environ.get("VPN_CHROME_PATH") or shutil.which("google-chrome"),args=["--no-sandbox"])
            admin=browser.new_context(viewport={"width":1440,"height":1000})
            admin.request.post(origin+"/admin/login",form={"password":"local-test-admin-password"},max_redirects=0)
            page=admin.new_page();errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(origin+"/admin/vpn");expect(page.locator("h1")).to_contain_text("Zentral verwaltet")
            page.screenshot(path=str(output/"vpn-admin-desktop.png"),full_page=True)
            page.locator("details.device > summary").first.click()
            expect(page.get_by_role("button",name="VPN sperren",exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),"Desktop overflow"
            page.screenshot(path=str(output/"vpn-admin-device.png"))
            search=page.locator("#device-search");search.fill("Familie Süd")
            expect(page.locator("details.device:visible")).to_have_count(1)
            search.fill("kein-passendes-geraet");expect(page.locator("#no-search-results")).to_be_visible()
            search.fill("")
            page.set_viewport_size({"width":390,"height":844})
            page.goto(origin+"/admin/vpn")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),"Mobile overflow"
            page.screenshot(path=str(output/"vpn-admin-mobile.png"),full_page=True)
            page.locator("details.device > summary").first.click()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),"Expanded mobile overflow"
            reseller=browser.new_context(viewport={"width":1440,"height":1000})
            reseller.request.post(origin+"/reseller/login",form={"username":"r1","password":"preview-reseller-password"},max_redirects=0)
            portal=reseller.new_page();portal.on("pageerror",lambda error:errors.append(str(error)))
            portal.goto(origin+"/reseller/vpn")
            expect(portal.locator("#order-total")).to_have_text("Gesamt: 32,50 €")
            portal.locator("#order-quantity").fill("4")
            expect(portal.locator("#order-total")).to_have_text("Gesamt: 13,00 €")
            assert "Familie Süd" not in portal.content()
            expect(portal.get_by_role("button",name="Preis speichern",exact=True)).to_have_count(0)
            portal.screenshot(path=str(output/"vpn-reseller-desktop.png"),full_page=True)
            assert not errors,errors
            browser.close()
        print(f"Desktop/Mobil, Gerätefilter, Formulare, Reseller-Sicht und Bestellsumme geprüft: {output}")
    finally:
        server.shutdown();fixture.doCleanups()


if __name__=="__main__":main()
