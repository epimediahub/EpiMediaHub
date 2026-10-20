"""Printable A4-landscape expiry checklist: renderer only, no database access.

The caller must supply *verified* user+playlist expiration dates.
No playlist URLs, passwords, hardware identifiers or access tokens are accepted.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PAGE_W,PAGE_H=landscape(A4)
L,R=35,807
COL=(35,246,350,474,604,807)
MONTHS=("","Januar","Februar","März","April","Mai","Juni","Juli",
        "August","September","Oktober","November","Dezember")

@dataclass(frozen=True)
class Expiry:
    customer: str
    playlist: str
    day: date


def _font():
    candidates=(
      ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","EpiExpiry"),
      ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf","EpiExpiryBold"),
    )
    for file,name in candidates:
        if name not in pdfmetrics.getRegisteredFontNames():
            if not Path(file).is_file():
                raise RuntimeError("PRINT_FONT_UNAVAILABLE")
            pdfmetrics.registerFont(TTFont(name,file))
    return "EpiExpiry","EpiExpiryBold"


def _fit(pdf,text,x,y,max_width,font,size):
    text=str(text)
    while text and pdfmetrics.stringWidth(text,font,size)>max_width:
        text=text[:-1]
    pdf.drawString(x,y,text)


def monthly_pdf(items:list[Expiry],year:int,month:int,output:Path):
    """Group by playlist, then expiry date; add large empty contact/date/notes fields.

    Each playlist starts on a new page. Never infer the date from a license or
    unrelated provider record. No PII in PDF metadata or return values.
    """
    if type(year) is not int or type(month) is not int or not 2000<=year<=2100 or not 1<=month<=12:
        raise ValueError("INVALID_PERIOD")
    groups=defaultdict(list)
    for item in items:
        if not isinstance(item,Expiry) or not isinstance(item.day,date) or isinstance(item.day,datetime):
            raise ValueError("INVALID_RECORD")
        if any(not isinstance(s,str) or not s.strip() or len(s)>200
               or any(ord(c)<32 for c in s) for s in (item.customer,item.playlist)):
            raise ValueError("INVALID_RECORD")
        if (item.day.year,item.day.month)==(year,month):
            groups[item.playlist].append(item)
    for rows in groups.values():
        rows.sort(key=lambda r:(r.day,r.customer.casefold()))
    plain,bold=_font()
    pdf=canvas.Canvas(str(output),pagesize=(PAGE_W,PAGE_H),pageCompression=1)
    pdf.setTitle("EpiMediaHub Monatsuebersicht "+str(year)+"-"+str(month).zfill(2))
    pdf.setAuthor("EpiMediaHub Admin")
    pages=0
    def heading(playlist,count,continued=False):
        nonlocal pages
        pages+=1
        pdf.setFillColorRGB(.09,.16,.25)
        pdf.rect(0,PAGE_H-86,PAGE_W,86,fill=1,stroke=0)
        pdf.setFillColorRGB(1,1,1)
        pdf.setFont(bold,15)
        pdf.drawString(L,PAGE_H-34,"EpiMediaHub  |  Ablaufübersicht")
        pdf.setFont(plain,9)
        pdf.drawRightString(PAGE_W-L,PAGE_H-33,
                            f"{MONTHS[month]} {year}  |  {count} Einträge")
        pdf.setFont(bold,11)
        _fit(pdf,"Playlist: "+playlist+(" (Fortsetzung)" if continued else ""),
             L,PAGE_H-63,PAGE_W-2*L,bold,11)
        pdf.setFillColorRGB(.3,.38,.48)
        pdf.setFont(plain,8)
        pdf.drawString(L,PAGE_H-104,
            "Nach Ablaufdatum sortiert  |  Freiraum für handschriftliche Einträge")
        top=PAGE_H-122
        pdf.setFillColorRGB(.9,.93,.96)
        pdf.roundRect(L,top-29,R-L,29,5,fill=1,stroke=0)
        pdf.setFillColorRGB(.09,.16,.25)
        for x,label in zip(COL,("Kundenname","Ablaufdatum","Kontaktiert",
                               "Termin / Uhrzeit","Notizen / Ergebnis")):
            pdf.setFont(bold,8)
            pdf.drawString(x+8,top-19,label)
        pdf.setFillColorRGB(.3,.38,.48)
        pdf.setFont(plain,7.5)
        pdf.drawString(L,31,"Vertraulich  |  Nur für berechtigte Administratoren")
        pdf.drawRightString(R,31,f"Seite {pages}")
        return top-29
    if not groups:
        top=heading("Keine bestätigten Abläufe",0)
        pdf.setFont(plain,11)
        pdf.drawString(L+10,top-48,"Für diesen Monat liegen keine bestätigten Abläufe vor.")
        pdf.showPage()
    for playlist in sorted(groups,key=str.casefold):
        rows=groups[playlist]
        y=0
        for i,entry in enumerate(rows):
            if i==0 or y-47<56:
                if i: pdf.showPage()
                y=heading(playlist,len(rows),i>0)
            next_y=y-47
            pdf.setFillColorRGB(*( (.965,.975,.99) if i%2==0 else (1,1,1) ))
            pdf.rect(L,next_y,R-L,47,fill=1,stroke=0)
            pdf.setStrokeColorRGB(.82,.86,.9)
            pdf.line(L,next_y,R,next_y)
            for x in COL[1:-1]: pdf.line(x,next_y,x,y)
            pdf.setFillColorRGB(.09,.16,.25)
            pdf.setFont(plain,9.5)
            _fit(pdf,entry.customer,L+8,y-26,COL[1]-L-16,plain,9.5)
            pdf.setFont(bold,9)
            pdf.drawString(COL[1]+8,y-26,entry.day.strftime("%d.%m.%Y"))
            pdf.setStrokeColorRGB(.5,.58,.67)
            pdf.rect(COL[2]+10,next_y+16,12,12,stroke=1,fill=0)
            pdf.setFont(plain,8)
            pdf.drawString(COL[2]+27,next_y+18,"Ja")
            pdf.line(COL[3]+10,next_y+13,COL[4]-12,next_y+13)
            pdf.line(COL[4]+10,next_y+13,R-12,next_y+13)
            y=next_y
        pdf.showPage()
    pdf.save()
    return {"month":f"{year}-{month:02d}","entries":sum(map(len,groups.values())),
            "playlists":len(groups),"pages":pages}
