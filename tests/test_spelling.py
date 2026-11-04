"""Offline spellchecker: typos corrected, valid words never touched."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
import spelling  # noqa: E402

# Fuzzy corrections (Symmetric Delete lookup, not the fixed map).
TYPO_FIXES = {
    "hakathon": "hackathon",
    "tommorow": "tomorrow",
    "seperate": "separate",
    "littel": "little",
    "occassion": "occasion",
    "neccessary": "necessary",
    "accomodation": "accommodation",
    "fourty": "forty",
    "twelvth": "twelfth",
    "beautifull": "beautiful",
    "happyness": "happiness",
    "developement": "development",
    "knowlege": "knowledge",
    "enviroment": "environment",
    "beleive": "believe",
    "freind": "friend",
}

# Exact-map corrections (checked before the fuzzy pass in _grammar_fixes).
MAP_FIXES = {
    "writting": "writing",
    "occured": "occurred",
    "recieve": "receive",
    "goverment": "government",
    "grammer": "grammar",
    "definately": "definitely",
    "writen": "written",
    "arguement": "argument",
    "managment": "management",
    "goed": "went",
    "maked": "made",
    "runing": "running",
    "stoped": "stopped",
}

# Valid words that must never be flagged.
VALID_WORDS = """
plants stories running children happiness development government panchayat
onasadya pookkalam pookalam vallamkali kathakali evaporation favourite
dialogue dialog twelfth physics chemistry biology stories written went gone
done seen taken given made came thought brought bought taught caught fought
found built sent spent meant slept kept felt stood understood born worn torn
chosen broken stolen forgotten hidden shaken mice lice geese oxen men women
feet teeth colour color favour favor honour honor behaviour behavior labour
labor neighbour neighbor flavour flavor humour humor rumour rumour favourite
favorite organise organize realise realize recognise recognize apologise
apologize emphasise emphasize summarise summarize analyse analyze criticise
criticize catalogue catalog programme program cheque grey gray tyre tire
kerb curb plough plow mould mold odour odor fibre fiber centre center
theatre theater litre liter metre meter travelling traveling cancelled
canceled labelled labeled modelled fulfil fulfill distil distill instal
install instalment installment enthral enthrall jewellery jewelry everyday
everybody everyone everything everywhere somebody someone something sometime
sometimes somehow anybody anyone anything anyway anytime anywhere nobody
nothing nowhere none morning evening night today tomorrow yesterday daily
weekly monthly yearly annually monday january february march april june july
august september october november december first second third twentieth
twelfth hundred thousand lakh crore million billion once twice thrice upon
into onto without within throughout inside outside itself himself herself
themselves ourselves yourselves myself yourself already although altogether
apart aside awake asleep abroad ahead along aloud around about above across
after against among between during under over again here there where which
who whom whose what why how all any both each few more most other some such
nor not only own same than too very can will just should now twin rewrite
reread practise practised learnt dreamed spelled smelled burned plastic
village river students nature bottles waste freedom struggle peace calm enjoy
public libraries helped many prepare college cricket fun watch sun rain grow
tall need carry far rivers fish shade trees climate festival wear clothes lay
flower carpets called families gather feast harvest school water food house
time year day ball stick elephant lion tiger bear wolf rabbit mouse frog snake
shark dolphin turtle tortoise crab oyster shrimp prawn squid penguin rhino
kangaroo reindeer santa fanta coke pepsi mirinda thumsup maaza frooti appy
fizz anda panda dragon castor worse worsen ball elephant octopus jellyfish
starfish seahorse lobster squid penguin rhino rhinoceros hippopotamus kangaroo
reindeer toward towards sulphur sulfur phosphorus potassium sodium calcium
magnesium aluminium aluminum cobalt platinum titanium chromium tungsten radium
radius uranium radon neon argon krypton xenon helium nitrogen fluorine
chlorine bromine plenty skilful wilful instill enroll courageous dangerous
nervous anxious mysterious victorious glorious tedious zealous rebellious
marvellous marvelous scandalous miraculous ridiculous meticulous vivacious
tenacious audacious fallacious lightening frightening misunderstood compliment
serial patience currant dual foreword navel peddle rein raze ray rote troupe
valence valance vial vise whey weed whet whit wrack reek wreak wring yore
canvass grisly grizzly hangar heroin jester lyre marshal spacious steppe tier
thyme tow vane wile teem creak sere serge cession napkin tablecloth bedsheet
pillowcase shampoo toothbrush toothpaste bucket utensil doormat garbage
cabbage atta maida rava suji poha upma vada sambar rasam kheer rabri kulfi
falooda chai kaapi pakora pakoda bhaji pani golgappa phuchka chaat tikki
kebab kabob tandoor tandoori pulao pilaf khichdi tamarind kokum buttermilk
lassi chaas sherbet sorbet nimbu shikanji achar papad papadam poppadom appam
puttu idiyappam pathiri kappa tapioca chembu chaya kattan payasam sadya
chenda melam thiruvonam thiruvathira perunnal ambalam palli pallikoodam
madrasa madrassa vidyalaya pathshala anganwadi balwadi sarpanch councillor
councilor counsellor counselor municipality operation cooperation corporation
collector visitor sailor traitor creator donor mentor juror sculptor inventor
investor auditor editor director inspector contractor conductor competitor
supervisor supervise advisor adviser senator dictator narrator translator
curator janitor pastor realtor surveyor purveyor conveyor doorstep footstep
doorman milkman fisherman policeman businessman chairman spokesman spokeswoman
statesman fireman handyman nobleman cameraman postmen milkmen fishermen
policemen businessmen chairmen spokesmen spokeswomen firemen doormen handymen
noblemen statesmen cameramen gentlemen gentlewoman gentlewomen zoology
geology astronomy astrology gastronomy economy economics civics geography
statistics accountancy entrepreneur accomplish establish marriage orphanage
vintage percentage mileage wastage hosteller hostelite supplementary
compartment backlog arrear revaluation photocopy photostat xerox stencil
fevicol roughbook fairbook scrapbook slambook lunchbox tiffin backpack
rucksack duffel duffle raincoat windcheater cardigan pullover mitten beanie
sweatshirt hoodie trenchcoat kurta salwar kameez churidar dupatta leggings
jeggings palazzo lungi mundu veshti sherwani nehru tagore kalam bose bhagat
singh kaur sharma verma gupta agarwal agrawal arun meera anita sunil deepa
kavya navya divya diya arjun rohan mohan sohan sneha pooja neha aman vikas
aditya ishan ishaan krishna radha sita gita geeta ramayana mahabharata
bhagavad veda upanishad purana roti naan kulcha bhatura thepla dhokla jalebi
laddu ladoo rasgulla rasogolla gulab jamun barfi burfi halwa halva veena
sitar tabla tanpura tambura harmonium kolam rangoli aarti bhajan kirtan
qawwali iftar sehri zakat roza puri paratha parotta porotta chapati chappati
ketchup tote carrybag paperbag darling sibling homesick seasick carsick
airsick handbag washroom cloakroom staffroom storeroom godown strongroom
acknowledge upward downward outward onward homeward northward southward
eastward westward madden maid ration certificate marksheet hallticket
admitcard classmate benchmate deskmate roommate teammate playmate schoolmate
soulmate checkmate prefect assembly attendance register classwork schoolwork
coursework fieldwork teamwork information baggage elsewhere upstairs
downstairs headmistress warden storey attic cellar terrace balcony verandah
veranda portico foyer lobby corridor gallery staircase elevator escalator
ramp railing banister bannister grill compound hedge ditch borewell tubewell
handpump sump overhead shelf rack almirah drawer trunk suitcase briefcase
flask thermos tumbler saucer basin ladle spatula rolling chakla belan tawa
kadhai frypan saucepan toaster mixer grinder fridge freezer burner lighter
matchbox geyser washing clothesline wiper duster dustpan screwdriver pliers
spanner axe hatchet sickle scythe pitchfork wheelbarrow twine thimble zipper
snap fastener hairpin paperclip staple stapler punch folder binder bulldog
paperweight bookmark highlighter pastel charcoal easel apron smock bib coaster
doily runner centrepiece flowerpot planter manure compost fertiliser fertilizer
pesticide insecticide fungicide herbicide weedkiller carpenter mason plumber
electrician welder painter sweeper watchman gardener bearer peon typist
stenographer receptionist cashier chairperson treasurer labourer coolie porter
loader constable superintendent commissioner magistrate advocate attorney
prosecutor defendant plaintiff jury verdict judgment judgement remand trial
hearing appeal petition lawsuit dispute challan summons warrant seizure arrest
acquittal conviction discharge dismissal suspension transfer posting promotion
demotion retirement gratuity bonus increment allowance conveyance earned
maternity sabbatical roster almanac timetable interval projector pointer atlas
specimen goggles litmus reagent alkali valency proton neutron nucleus orbit
shell formula equation reactant transistor processor smartphone charger webcam
tripod teddy yoyo marbles hopscotch skipping kho squash racquet stump jersey
referee semifinal quarterfinal wicket sixer boundary century duck innings
declaration toss floodlight scorer scoreboard announcer cheerleader placard
slogan chant anthem punctuality honesty nonviolence tolerance fable parable
ballad couplet sonnet ode elegy satire mime melody harmony tempo raga tala
dholak ghatam kanjira morsing nadaswaram shehnai saxophone trombone clarinet
oboe bassoon harmonica accordion casio harp banjo mandolin ukulele cymbals
tambourine maracas bongo xylophone chime bugle conch shankh damru dhol tasha
djembe thavil udukai parai pulikali kummi kolattam dandiya garba bhangra
giddha lavani tamasha nautanki jatara bhavai nukkad monoact mimicry prop
backdrop wings applause encore critic editorial byline dateline caption cartoon
crossword sudoku horoscope matrimonial obituary tender auction cashback coupon
voucher loyalty shipping courier parcel packet stamp seal letterhead visiting
invitation mithai faral chakli murukku thattai namkeen bhujia thokku chutney
podi garam masala chilli methi fennel saunf cardamom elaichi dalchini anise
mace asafoetida hing pippali sukku poppy til gingelly groundnut vanaspati
dalda malai paneer chenna khoa mawa yogurt toned skimmed condensed booth
parlour kirana supermarket hypermarket mandi sabzi shandy mela expo founders
janmashtami shivratri thaipusam panguni uthiram baisakhi vaisakhi bihu bohag
rongali poila shital sarhul navakhai nuakhai parba chhath teej karva bandhan
govardhan satyanarayan kumbh magh shravan sawan aadi thai maasi purattasi
aippasi margazhi mattu kaanum bhogi kandeel akash pharal karanji shankarpali
besan motichoor boondi jangri imarti katli rasmalai chamcham sandesh payesh
phirni sevaiyan khurma meetha tehri bisibelebath sarkarai pulihora daddojanam
gongura pachadi avakaya majjiga tumbler dabara davara kumbakonam madras
kachori dabeli misal usal khari osmania rusk nankhatai maska ladi kadak brun
irani samovar kehwah kahwa sulaimani suleimani chukku panangkarkandu
karupatti marayoor kanthari mulaku kariveppilai karapincha murungai vendakkai
bhindi okra kathirikai baingan pavakkai padaval poosanikai parangikai sorakkai
peerkangai turai parwal tindora kovakkai kothavarangai avarakkai pattani
chickpea kabuli kala pachai ulundu tuvaram kadalai siruparuppu ulutham kollu
matki lobia karamani cowpea soyabean verkadalai nilakadalai mundiri badam
pista pistachio akhrot kishmish khajur anjeer khubani perikai santra mosambi
elumichai thiratchai mathulai pappali koyya palapazham vazhapazham nendran
robusta poovan rasthali annasi muskmelon cantaloupe seethapazham soursop
mulluseetha vilampazham jambakka jambu carambola kiwi avocado sapota chikoo
chickoo litchi lychee rambutan mangosteen breadfruit seema elaneer karikku
nungu toddy kallu neera padaneer karumbu vellam bella gul shakkar khandsari
thene treacle molasses agave toor chana aloo anda panda santa fanta coke
pepsi mirinda thumsup maaza frooti appy fizz toward towards worse worsen
gladden tighten loosen fasten hasten moisten christen glisten harken roughen
toughen coarsen hoarsen
""".split()


def test_common_typos_corrected():
    for bad, good in TYPO_FIXES.items():
        assert spelling.correction(bad) == good, bad


def test_map_corrections_apply():
    for bad, good in MAP_FIXES.items():
        fixes = main._grammar_fixes(f"Plants grow well and {bad} daily")
        assert fixes, bad
        assert fixes[0]["right"] == \
            f"Plants grow well and {good} daily", bad
        assert fixes[0]["rule"] == f"The spelling is '{good}'.", bad


def test_valid_words_untouched():
    bad = [w for w in VALID_WORDS if spelling.correction(w) is not None]
    assert bad == [], [(w, spelling.correction(w)) for w in bad[:12]]


def test_names_and_caps_untouched():
    for token in ("Onam", "Arun", "Meera", "Kerala", "Rahul", "Priya",
                  "TV", "CBSE", "NASA", "iPhone", "eBay"):
        assert spelling.correction(token) is None, token


def test_short_tokens_untouched():
    for token in ("the", "and", "yes", "ok", "tv", "an", "a", "1234",
                  "word1", "co2"):
        assert spelling.correction(token) is None, token


def test_grammar_fixes_flag_spelling():
    fixes = main._grammar_fixes("Trees give shade but hakathon fails daily")
    assert fixes, "mid-sentence typo must be flagged"
    assert fixes[0]["right"] == \
        "Trees give shade but hackathon fails daily"
    assert fixes[0]["rule"] == "The spelling is 'hackathon'."


def test_known_misspellings_win_over_fuzzy():
    fixes = main._grammar_fixes("Plants need water for writting well")
    assert fixes[0]["right"] == "Plants need water for writing well"


def test_two_word_splits():
    fixes = main._grammar_fixes("Plants need alot of water daily")
    assert fixes[0]["right"] == "Plants need a lot of water daily"
    assert fixes[0]["rule"] == "The spelling is 'a lot'."
    fixes = main._grammar_fixes("Plants grow inspite of dry days")
    assert fixes[0]["right"] == "Plants grow in spite of dry days"


def test_irregular_verb_typos():
    fixes = main._grammar_fixes("Plants goed dry in summer days")
    assert fixes[0]["right"] == "Plants went dry in summer days"
    fixes = main._grammar_fixes("Plants maked food from sunlight")
    assert fixes[0]["right"] == "Plants made food from sunlight"


def test_capital_and_spelling_combined():
    fixes = main._grammar_fixes("hakathon are fun events yearly")
    assert len(fixes) == 1
    assert fixes[0]["right"] == "Hackathon are fun events yearly"
    assert "capital letter" in fixes[0]["rule"]
    assert "hackathon" in fixes[0]["rule"]


def test_model_rewrite_fixes_spelling():
    text = "Plants grow well daily. Coders join hakathon events yearly."
    model = main._template_model(text)
    assert model is not None
    assert "hackathon" in model["after"]
    assert "hakathon" not in model["after"]
    assert model["before"] in text


def test_mechanics_module_title():
    titles = [m["title"] for m in main.CURRICULUM_MODULES
              if m["id"] == "mechanics"]
    assert titles == ["Mechanics of writing"]
