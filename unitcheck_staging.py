import sys
sys.path.insert(0, r"C:\Users\Admin\vibeedutwin")
import main

fails = 0
def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print("OK " if ok else "FAIL", name, "" if ok else (repr(got) + " want " + repr(want)))

check("caps-colon", main.clean_excerpt_text(
    "TECHNICAL BACKGROUND: some reports need data here."), "")
check("nasa", main.clean_excerpt_text(
    "NASA: Mars missions continue today here."), "Mars missions continue today here.")
check("xref-edition", main.clean_excerpt_text(
    "See Edition 233 technical notes today."), "")
check("version-kept", main.clean_excerpt_text(
    "Version 22 released today here."), "Version 22 released today here.")
check("bare-heading", main.clean_excerpt_text("References."), "")
check("intro-psy", main.clean_excerpt_text("Introduction to Psychology."),
      "Introduction to Psychology.")
check("it-open", main.clean_excerpt_text(
    "It should open with an introduction here."), "")
check("it-open-soon", main.clean_excerpt_text(
    "It should open soon after repairs."), "It should open soon after repairs.")
check("it-contain", main.clean_excerpt_text(
    "It should contain data and evidence."), "")
check("it-follow", main.clean_excerpt_text(
    "It should follow a logical structure here."), "")
check("it-follow-soon", main.clean_excerpt_text(
    "It should follow soon after that."), "It should follow soon after that.")
check("show-should", main.clean_excerpt_text(
    "The show should end with a bang."), "The show should end with a bang.")

repairs = [
    ("Write a per suasive essay today.", "Write a persuasive essay today."),
    ("She spoke per suasively to voters.", "She spoke persuasively to voters."),
    ("The organi zation meets weekly now.", "The organization meets weekly now."),
    ("Civil ization advances through trade.", "Civilization advances through trade."),
    ("Na tion building takes decades here.", "Nation building takes decades here."),
    ("Vi sion matters for leaders today.", "Vision matters for leaders today."),
    ("Real ize your goals this year.", "Realize your goals this year."),
    ("They stud ied late last night.", "They studied late last night."),
    ("Good law yers argue clearly here.", "Good lawyers argue clearly here."),
    ("Form ation flying looks amazing.", "Formation flying looks amazing."),
    ("Take immediate a ction today now.", "Take immediate action today now."),
    ("Sea port cities grow fast now.", "Sea port cities grow fast now."),
    ("Sodium ion levels rise daily now.", "Sodium ion levels rise daily now."),
]
for raw, want in repairs:
    check("rep:" + raw[:28], main.clean_excerpt_text(raw), want)
print("fails:", fails)
