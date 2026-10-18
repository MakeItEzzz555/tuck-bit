#!/usr/bin/env python3
"""Generate a self-hosted editorial routing diagram for TuckBit's GitHub README.

No runtime scripts, fonts, gradients, external references or network dependencies.
A deliberately unified signal-flow composition replaces three ordinary cards.
"""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "assets" / "branding"
XMLNS = "http://www.w3.org/2000/svg"
ET.register_namespace("", XMLNS)

def T(local):
    return "{" + XMLNS + "}" + local

PALETTES = {
    "dark": {"bg": "#090F19", "surface": "#14243A", "fg": "#F5F9FF",
             "secondary": "#C0CFE2", "quiet": "#748AA5", "line": "#344961",
             "blue": "#4C9BFF", "blue_dim": "#194B87", "white": "#FFFFFF"},
    "light": {"bg": "#FFFFFF", "surface": "#E6F0FD", "fg": "#142338",
              "secondary": "#344B67", "quiet": "#556C85", "line": "#BBCDE3",
              "blue": "#146BE8", "blue_dim": "#A7CFFB", "white": "#FFFFFF"},
}

def element(parent, local, **attributes):
    return ET.SubElement(parent, T(local), {k.replace("_", "-"): str(v) for k, v in attributes.items()})

def rect(parent,x,y,w,h,c,rx=0):
    return element(parent,"rect",x=x,y=y,width=w,height=h,rx=rx,fill=c)

def path(parent,d,stroke,width=2,fill="none",opacity=1):
    return element(parent,"path",d=d,fill=fill,stroke=stroke,stroke_width=width,
                   opacity=opacity,stroke_linecap="round",stroke_linejoin="round")

def line(parent,x1,y1,x2,y2,color,width=1,opacity=1):
    return element(parent,"line",x1=x1,y1=y1,x2=x2,y2=y2,stroke=color,stroke_width=width,opacity=opacity)

def text(parent,x,y,s,size,color,weight=400,letter_spacing=0,anchor="start"):
    obj=element(parent,"text",x=x,y=y,fill=color,font_family="Arial,Helvetica,sans-serif",
                font_size=size,font_weight=weight,letter_spacing=letter_spacing,text_anchor=anchor)
    obj.text=s
    return obj

def dot(parent,x,y,r,color):
    return element(parent,"circle",cx=x,cy=y,r=r,fill=color)

def heading(root, palette, mobile):
    c=palette
    if mobile:
        text(root,40,73,"Make every tool",43,c["fg"],700,-1.3)
        text(root,40,119,"call count.",43,c["blue"],700,-1.3)
        text(root,40,157,"Scope what matters. Keep every required check.",20,c["secondary"])
    else:
        text(root,44,69,"Make every tool call count.",45,c["fg"],700,-1.5)
        text(root,46,107,"Scope what matters. Keep every required check.",20,c["secondary"])
        text(root,1110,69,"TUCKBIT / EXECUTION PATH",14,c["quiet"],700,1.0,"end")

def signature(root,c,mobile):
    if mobile:
        text(root,40,813,"Advisory guidance. Native permissions remain authoritative.",17,c["quiet"])
    else:
        line(root,44,364,1115,364,c["line"],1)
        text(root,44,391,"Agent-native permissions remain authoritative.",16,c["quiet"])
        text(root,1116,391,"INTENT    ·    ROUTING    ·    EVIDENCE",14,c["quiet"],600,1,"end")

def desktop(root,c):
    # The input staff visibly carries the task, context, and constraints together.
    text(root,44,181,"Original request",29,c["fg"],700,-0.5)
    text(root,45,210,"Task, constraints, approved tools",18,c["secondary"])
    text(root,45,244,"Nothing important gets discarded.",16,c["quiet"])
    source_y=[280,304,328]
    for i,y in enumerate(source_y):
        dot(root,50,y,5,c["blue"] if i==1 else c["quiet"])
        line(root,59,y,330,y,c["blue"] if i==1 else c["line"],3 if i==1 else 2)

    # Incoming staff arcs merge into one editorial selection lens.
    path(root,"M330 280 C412 280 435 304 501 304",c["line"],2)
    path(root,"M330 304 H501",c["blue"],3.5)
    path(root,"M330 328 C414 328 435 304 501 304",c["line"],2)
    dot(root,501,304,6,c["blue"])

    # Routing gateway: not a box. Its nested open rings imply right-size discovery.
    element(root,"circle",cx=561,cy=304,r=47,fill=c["bg"],stroke=c["line"],stroke_width=2)
    path(root,"M531 328 C511 306 525 274 549 268",c["blue"],5)
    path(root,"M580 271 C604 292 598 319 574 337",c["blue"],5)
    path(root,"M550 304 H572 M562 296 L572 304 562 312",c["fg"],4)
    text(root,561,236,"Select relevant context",23,c["fg"],700,-0.2,"middle")
    text(root,561,258,"and tools on demand",17,c["secondary"],400,0,"middle")

    # Signal goes all the way through to verification, not a dropped/short-cut trail.
    path(root,"M608 304 H786 C816 304 822 286 844 286",c["blue"],3.5)
    dot(root,844,286,6,c["blue"])

    text(root,846,182,"Verified handoff",29,c["fg"],700,-0.5)
    text(root,846,211,"Required checks stay intact",18,c["secondary"])
    for y,label in [(258,"Correct outcome"),(291,"Native approvals"),(324,"Evidence receipt")]:
        element(root,"circle",cx=854,cy=y-5,r=9,fill=c["surface"])
        path(root,f"M849 {y-5} L853 {y-1} L860 {y-10}",c["blue"],2.5)
        text(root,873,y,label,18,c["fg"])

    # Editorial micro rail anchors the graphic without faux statistics or UI cards.
    line(root,44,139,1116,139,c["line"])
    text(root,44,129,"REQUEST",12,c["quiet"],700,1.8)
    text(root,561,129,"FOCUSED DISCOVERY",12,c["quiet"],700,1.8,"middle")
    text(root,1116,129,"REQUIRED VERIFICATION",12,c["quiet"],700,1.8,"end")

def mobile(root,c):
    # Vertical composition: purposeful editorial type and a single line of motion.
    text(root,40,214,"The complete request",29,c["fg"],700,-0.5)
    text(root,40,247,"Constraints and permissions stay intact.",19,c["secondary"])
    for yy in (284,305,326):
        dot(root,54,yy,4,c["blue"] if yy==305 else c["quiet"])
        line(root,62,yy,278,yy,c["blue"] if yy==305 else c["line"],3 if yy==305 else 2)
    # A bundled column funnels into the focus lens, then carries forward.
    path(root,"M278 284 C327 284 342 320 342 367",c["line"],2)
    path(root,"M278 305 C317 305 342 324 342 367",c["blue"],3.5)
    path(root,"M278 326 C307 326 342 338 342 367",c["line"],2)
    line(root,342,367,342,415,c["blue"],3.5)
    element(root,"circle",cx=342,cy=452,r=38,fill=c["bg"],stroke=c["line"],stroke_width=2)
    path(root,"M318 468 C300 445 319 423 332 419",c["blue"],4)
    path(root,"M352 421 C375 434 367 465 352 480",c["blue"],4)
    path(root,"M329 452 H350 M342 445 L350 452 342 459",c["fg"],3)
    text(root,40,385,"Focus the work",30,c["fg"],700,-0.5)
    text(root,40,413,"Relevant context and tools.",19,c["secondary"])
    line(root,342,490,342,562,c["blue"],3.5)
    path(root,"M342 562 C342 584 324 592 310 592 H64",c["blue"],3.5)
    dot(root,64,592,6,c["blue"])
    text(root,40,637,"Verify and hand off",30,c["fg"],700,-0.5)
    text(root,40,668,"Required tests and evidence.",19,c["secondary"])
    for x,label in [(44,"Checks"),(234,"Approvals"),(422,"Receipt")]:
        dot(root,x+7,711,7,c["blue"])
        text(root,x+22,718,label,17,c["fg"],600)

def generate(theme,mobile):
    c=PALETTES[theme]
    width,height=(600,840) if mobile else (1160,410)
    root=ET.Element(T("svg"),{"width":str(width),"height":str(height),
        "viewBox":f"0 0 {width} {height}","role":"img",
        "aria-labelledby":"title desc"})
    element(root,"title",id="title").text="TuckBit: from intent to a verified result"
    element(root,"desc",id="desc").text=(
        "The full user request, constraints and permissions feed into scoped tool and "
        "context selection; mandatory checks and evidence stay in the final handoff."
    )
    rect(root,0,0,width,height,c["bg"])
    heading(root,c,mobile)
    if mobile:mobile_fn=globals()["mobile"];mobile_fn(root,c)
    else:desktop(root,c)
    signature(root,c,mobile)
    return ET.tostring(root,encoding="utf-8",xml_declaration=False)+b"\n"

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--check",action="store_true")
    args=a.parse_args()
    for theme in ("light","dark"):
        for is_mobile in (False,True):
            dest=DEST/("tuckbit-flow-"+theme+("-mobile" if is_mobile else "")+".svg")
            expected=generate(theme,is_mobile)
            if args.check:
                if not dest.exists() or dest.read_bytes()!=expected:
                    raise SystemExit(f"Regeneration mismatch: {dest}")
            else:
                dest.write_bytes(expected)
            ET.fromstring(expected)
            print(("Validated" if args.check else "Generated"),dest.name,len(expected),"bytes")
if __name__=="__main__":
    main()
