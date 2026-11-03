import sys
sys.path.insert(0, r"C:\Users\Admin\vibeedutwin")
import main

junk_cases = [
    ("Its purpose is to present and analyze information here.", True),
    ("The purpose of this essay is to argue a claim here.", True),
    ("My purpose is to win every game today.", False),
    ("His aim is true and steady here.", False),
    ("Supportable using available evidence and reasoning.", True),
    ("Available evidence and reasoning support claims.", False),
    ("For example, in his report on the products.", True),
    ("For example, zoos should be banned to protect animals.", False),
    ("For example, suppose your manager is busy today.", False),
    ("For example, write a report recommending open textbooks.", False),
    ("For example, state the thesis clearly today.", True),
    ("For example, he goes far away today.", False),
    ("For example, he writes.", False),
    ("For example, labs open every report with findings.", False),
]
fails = 0
for raw, want_junk in junk_cases:
    is_junk = main.clean_excerpt_text(raw) == ""
    ok = is_junk == want_junk
    fails += not ok
    print("OK " if ok else "FAIL", repr(raw[:55]),
          "" if ok else ("want junk=" + str(want_junk)))
print("fails:", fails)
