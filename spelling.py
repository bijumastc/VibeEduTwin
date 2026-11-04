"""VibeEduTwin offline spellchecker: curated words plus delete lookup.

No network and no third-party package: about 7,000 hand-checked base
words in frequency tiers, expanded with regular inflections at import,
corrected with Symmetric Delete lookup and a capped distance check.
Only confident fixes come back (distance 1, or 2 for longer words);
anything else returns None so valid words are never "corrected".
Callers pass single tokens; only all-lowercase words are checked, so
names (Onam, Arun) and acronyms (TV) are always left alone.
"""

# Tier 0: core function words and the most common verbs, nouns and
# adjectives. Every everyday word a learner writes should be here.
_TIER_0 = """
a able about above across after again against age ago air all allow almost
alone along already also always am among an and angry animal another answer
any anyone anything anywhere apart appear apply are area around arrive art
article as ask ate avoid aware away back bad base basic be became because
become been before begin began behind being believe belong below best better
between big bird birth birthday bit black blame blank bleed bless blind block
blood blow blue board boat body bold book born borrow both bottle bottom
bought bound box boy brain branch brave bread break breakfast breathe brick
bridge brief bright bring broad broke broken brown brush build built burn
burned burnt bus busy but buy by call calm came can cannot car care carry
case catch caught cause cell centre center certain chain chair chance change
charge chase cheap check cheese chief child children choice choose chose
chosen church circle city claim class clean clear clerk clever climb clock
close cloth clothes cloud coach coast coat cold collect college colour color
comb come comfort command common company compare complete concern conclude
condemn condition conduct confess confuse congratulate connect consider
consist contact contain content continue control cook cool copy corner
correct cost cottage cotton cough could count country courage course court
cousin cover cow crack craft crash crazy cream create crime crisis cross
crowd crown cruel crush cry curious current cut daily dance danger dare dark
data date daughter day dead deaf deal dear death debate decide deep defeat
defend define degree delay deliver demand dense deny depend depth derive
describe desert deserve design desire desk detail develop dial diary did die
differ different difficult dig direct dirty discuss disease dish dismiss
distant divide do doctor does dog done door doubt down dozen draft drain
drama drank dream dreamed drink drive driver drop drug drunk dry due dull
dust duty each ear early earn earth ease east easy eat edge effect effort egg
eight either elbow elder elect empty end enemy energy engine enjoy
enough enter entire entry equal error escape essay even evening event ever
every everyone everything exact examine example excellent except excite
excuse exist expect explain explore express extra eye face fact fail faint
fair faith fall false familiar family famous far farm fashion fast fat fault
favour favor fear feast feather feature fee feed feel feet fell fellow felt
fence festival fetch fever few field fierce fifteen fifth fifty fight figure
file fill film final find fine finger finish fire first fish fit five fix
flag flame flash flat flavour flavor flesh flew flight float flood floor
flour flow flower fluid fly focus fold folk follow food fool foot force
forest forget forgive fork form forty forward found four fourteen fourth
free freedom fresh friend frighten frog from front fruit full fun furnish
further future gain game garden gas gate gather gave general gentle girl
give glad glass glove go goes goal goat gold good goods got govern
grab grace grade grain grand grant grape grass grateful grave gray great
green greet grief ground group grow guard guess guest guide habit hair half
hall hand handle hang happen happy hard harm harsh has hate have he head
heal health hear heard heart heat heaven heavy height held hell help hence
her herd here hero hesitate hide high hill hint hire his history hit hold
hole holiday hollow home honest honey honour honor hope horse hospital hot
hotel hour house how however huge human humble hunger hunt hurry hurt
husband ice idea ideal if ignore ill image imagine important improve in inch
include income increase indeed index indicate indoor inner input inside
instead instruct insult intact invent invite iron island issue it its itself
jealous join joint joke journey joy judge juice jump just keen keep kept key
kick kind king kiss kitchen knew knock know knowledge known label labour
labor lack ladder lady laid lake lamp land large last late laugh law lay
lazy lead leader leaf learn least leave led left leg lend length less lesson
let letter level library lie life lift light like likely limit line link lion
liquid list listen little live lively load loaf local lock lodge logic
lonely long look loose lose loss lost lot loud love low loyal luck lump
lunch lying machine made magic mail main major make male man manage manner
many march mark market marry mask master match material matter may maybe me
meal mean means meant measure meat meet melt member memory mental mention
mere merry message met metal method middle might mild milk million mind mine
minus minute mirror miss mistake mix model modern modest moment money month
mood moon moral more morning most mother motion motor mountain mouse mouth
move much mud multiply murmur muscle music must my myself nail name narrow
nation native near neat necessary neck need needle neglect neighbour
neighbor neither nerve never new news next nice night nine nineteen ninety
no noble nobody noise none noon nor normal north nose note nothing notice
noun novel now nowhere number nurse oar obey object obtain obvious occasion
occur odd of off offer office often oil old on once one onion only onto
open operate opinion oppose option orange order organ other ought ounce our
ours out outdoor outside over overcome owe own owner oxygen page paid pain
paint pair palace pale palm paper parade pardon parent park part party pass
past paste path patient pattern pause pay peace peaceful peak pen pencil
people pepper per perfect perform perhaps period permit person phrase pick
picture piece pierce pile pilot pitch pity place plain plan plane plant
plate play pleasant please plenty plough plow pluck plug pocket poem poet
poetry point poison polar pole police polish polite pool poor popular
portion port pose position pound pour power practise practice praise pray
precious prefer prepare present press pretty prevent price pride priest
print prior prison private prize probable problem proceed produce product
profit programme program promise prompt proof proper proud prove provide
public pull pulse punch punish pupil pure purple purpose push put puzzle
quality quantity quarrel quart queen question quick quiet quilt quit quite
quote race radio rain raise range rank rapid rare rate rather reach react
read ready real realise realize reason recall receive recent reckon record
red reduce refer refresh refuse regard region regret regular reign relate
relax relay release relief rely remain remark remedy remember remind remote
remove render renew rent repair repeat reply report request rescue resemble
resent reserve resolve respect rest result return reveal revenge review
reward rhyme ribbon rice rich rid riddle ride right rigid rinse rise risk
river roar roast rob rock rode role roll roof room root rope rose rough
round rouse route royal rub rude rule ruler rumour rumor run rural rush
sad safe said sail saint sake salad salary sale salt same sand satisfy save
saw say scale scene scent scheme school science score scorn scrap scream
screen screw sea search season seat second secret section see seed seek seem
seen seldom select self sell send sense sent sentence separate serve set
settle seven severe shade shadow shake shall shallow shame shape share sharp
she sheep sheet shelf shell shelter shift shine ship shirt shock shoe shook
shoot shop shore short should shout show shower shut shy sick side sight
sign signal silent silly silver similar simple since sing singer single sink
sir sister sit site six sixth sixty skill skin skip skirt sky slave sleep
slept slice slide slight slim slip slope slow small smart smell smile smoke
smooth snake snap snow so soap soar sober social soft soil solar soldier
sole solemn solid solve some somebody somehow someone something sometime
son song soon sore sorrow sort soul sound south space spare spark speak
special speech speed spell spend spent spice spill spin spirit spite split
spoil spoke spoken spoon sport spot spread spring square stable staff stage
stain stair stamp stand star stare start state station stay steady steal
steam steel steep steer stem step stick stiff still sting stir stock stone
stood stool stoop stop store storm story stove straight strange straw stray
stream street strength stretch strict strike string stripe strive stroke
strong struggle student study stuff stump subject submit succeed such
sudden suffer sugar suggest suit sum summer sun supper supply support
suppose sure surface surprise survive suspect sweet swell swift swim sword
table tail take taken tale talent talk tall tame taste taught tax teach
team tear tease teeth tell temper temple tempt ten tend tender tenth term
terrible test than thank that the their them theme then there these thick
thief thin thing think third thirst thirteen thirty this thorn those
though thought thousand thread threat three threw throat through throw
thumb thunder tie tiger tight till time tin tiny tired title to today toe
together told tomorrow tone tongue tonight too took tool tooth top total
touch tough tour tower town trace track trade trail train trait travel tray
treat tree tremble trial tribe trick trim trip triumph troop trouble truck
true trust truth try twelve twenty twice twin twist type ugly uncle under
understand unit unite until untrue up upon upper upset urban urge urgent
use usual utter vacant vague valid valley value various vary vast veil verb
verse very vessel victory video view village vine visit visitor vital vivid
voice vote voyage wage waist wait wake walk wall wander want war warm warn
waste watch water wave way we weak wealth wear weather weave wed wedding
week weigh weight welcome well went were west wet what wheat wheel when
whence where whether which while whisper white whole whose why wicked wide
widow width wife wild will win wind window wine wing winner winter wipe
wire wisdom wise wish with withdraw within without witness woman women
wonder wood wool word wore work worker world worry worth would wound
wove woven wrap wrath wreath wreck wrench wrest wrestle write writer
writhe wrong wrote yard yarn year yell yellow yes yet yield yoke young
your yours youth zero
""".split()

# Tier 1: everyday life - home, food, nature, school, body, travel, feelings.
_TIER_1 = """
absent absolute absorb accept access accident accountant ache achieve acid
across actor actress adapt address admire admit adopt adore adorn adult
advance advantage adventure advertise advice advise aeroplane affair affect
agent agile agree ahead alarm album alert algebra alien alike alive all
allergy alley allow alloy alone aloud alphabet alter altar although
altitude altogether always amateur amaze ambition ambulance amend among
amount amuse analyse analyze anchor ancient angel anger angle ankle
announce annoy annual anthem anthropology anxious apart apology appeal
appease appetite applaud appoint approve apricot apron apt aqua arch argue
arise arithmetic arm arrange array arrest arrive arrow aside asleep aspect
aspire aspirin assault assemble assert assess asset assign assist assume
assure astonish astray asylum athlete atlas attach attack attain attempt
attend attic attract audience aunt author autumn avenue awake award aware
awful awkward axle bacon badge bad bank banner banquet bar bare bargain barge
barrel barrier basin basket bath bathe battle bay bazaar beach bead beak
beam bean beard beast beat beautiful beauty because become bedroom bee beef
before beg behave behaviour behavior behind beige being belch belief bell
belly bench bend beneath berth beside besiege best betray better beverage
beware beyond bicycle billow bin bind biology biscuit bison bite bitter
blade blink bliss blister block blog bloom blossom blouse blur blush board
boast boat boil bold bolt bond bone bonus book booth boot border bore borrow
boss botany bottle bounce bouquet bowling bracelet brag brake branch brand
brass brave brawl breakfast breast breath breeze brick bridal bride bridge
brief bright brisk broad bronze brood brook broom brother brought
budget buffet bulb bulk bull bunch bundle burden bureau burglar burn burst
bury bush butter button buyer cabin cable cactus cage cake
calendar calm camel camera camp campus canal cancel cancer candle candy cane
capable capital captain carbon card career carpet carriage carry carton
carve cascade cash caste castle casual cattle cause caution cave cease
ceiling cell cement census cereal ceremony chain chalk challenge chamber
chance change channel chant chaos chap chapter character charge charity
charm chart chase chasm chat cheap cheat check cheer cheese chef chemist
chess chest chew chick chicken chief child chimney chirp choke chocolate
choke choose chop chord chorus chronic chuckle church churn cider cinema
cinnamon circle circus cite citizen claim clap clarify clash clasp class
classic classify clause claw clay clean clear clerk clever click cliff
climate climb clinic clip cloak clock clone closet cloth cloud clown club
clumsy coach coal coarse coast coat cobra cockroach cocoa coconut coil coin
cold collar colleague collect colony column comb comedy comfort comic comma
command comment commerce commit common commotion compact company compare
compass compete compile complain complete complex compose compel compete
complain concert conclude concrete condemn conduct confer confess confide
confirm conflict confuse congeal congratulate connect conquer consent
conserve consider consist console conspire constant consult consume contact
contain contempt contend content contest continent continue contract
contrary contrast convene coral cord core cork corn corner corpse correct
corridor cost costume cottage cotton couch cough council counsel count
counter couple courage course court cousin crack cradle craft crane crash
crate crawl crayon crazy cream create crease credit creek creep crest crew
cricket crime crisp critic crocodile crop cross crowd crown cruel cruise
crumb crush crust crutch cry crystal cub cupboard curb cure curiosity curl
current curtain curve cushion custom customer cycle cyclone daily dairy
daisy damp dance dandruff danger dapple dare dash date dawn daylight dazzle
deadly deaf dean dear debate debit decay deceive decent decide decimal
decision deck declare decorate decrease decree dedicate deduce deed deem
deep deer defeat defend define degree delay delegate delete deliberate
delicate delight deliver delta demand demolish dense dent dental depart
depend depict deploy deposit depth deputy derive descend describe desert
deserve design desire desk despair despise despite dessert destiny detail
detain detect develop device devil devote dew diagram dial dialogue dialog
diameter diamond diary dictate diesel diet differ dig digest digit dilute
dim dine dinner dip direct dirty disable agree disappear disaster disco
discount discover discuss disease disguise disgust dish dishonest disk
dismiss disorder disperse display dispute dissolve distance distant distil
distress disturb ditch dive diverse divert divide dizzy dizzy doctor
dodge does doll dolphin domain donate donkey doom dot double doubt dough
dove down dozen draft drag drain drama drape drastic drawer dream dress
dried drift drill drink drip drive drizzle drone droop drop drought drown
drum drunk dry duck due dug dull dumb dump dune dung dusk dust dutiful duty
dwarf dwell dye eager eagle ear earn earnest earth earthquake ease easel
east easy echo eclipse ecology elbow elder elect eleven elite else embark
embassy ember emblem embody embrace emerge employ empty enable enact
enamel encircle encore endless endure enemy energy engage engine enjoy
enlarge enlighten enlist enormous enough enquire enrich enrol enter
entertain entire entrance entreat entry envelope envy epic epidemic equal
equip era erase erect error erupt escape essay essence estate esteem
eternal ethic ethnic evaporate even event ever every evict evil evolve exact
exalt exam examine excavate exceed excel except excess exchange excite
exclaim exclude excursion excuse exempt exile exist exit exotic expand
expect expense expert expire explain explode exploit explore export expose
express extend extra extract extreme eyebrow fabric fable facet fail faint
fair fairy faith fake fall false fame family famine famous fan fancy far
fare farm fascinate fashion fast fasten fatal father fathom fatigue fault
favour favorite favourite feast feather feature February fee feeble feed
feign fell fellow felt fence fern ferry fertile fetch fever fibre fiber
fickle fiction fiddle field fierce fiery fifteen fifth fifty fig fight figure
filament file fill fillet film filter fin final finance find fine finger
finish finite fir fire firm first fiscal fish flame flank flare flash flask
flat flavour flea flee fleet flesh flew flex flick fling float flock flood
flop flora flour flourish flow flower fluid flush flute flutter focus fodder
fog foil fold folk follow fond food fool foot force forecast forehead
foreign forest forge forget forgive fork form formal format former forty
forum forward fossil foster foul fought found fountain four fourteen fourth
fowl fox fraction fragile fragrant frail frame frank fraud freckle free
freeze freight French frenzy fresh fret friar friction Friday friend
fright fringe frock frog frost frown frozen fruit frustrate fry fudge fuel
fulfil fulfill full fumble fume fun fund funeral fungus funnel funny fur
furious furnish furniture further fury fuse fuss future gadget gain gait
galaxy gallant gallery gallon gallop gang gap garage garden garlic garment
gasp gate gather gauge gaze gear gem gender gene general generous genius
genre gentle germ giant gift ginger giraffe girl glacier glad glance gland
glare glass gleam glide glimpse glitter globe gloom glory glove glow glue
gnat gnaw goal goat golden golf gone good gorge gorgeous gossip gourd govern
gown grab grace grade gradual grain gram grammar grand grant grape grasp
grass grateful grave gravel gravity graze grease great greed green greet
grief grill grim grin grind grip groan grocer groom groove grope gross
ground group grove growl grown growth grudge grumble grunt guard guess
guest guide guild guilt guise guitar gulf gum gust gut guy habit hail hair
half hall halt hamlet hammer hamper hand handful handle handsome handy hang
harbour harbor hard hardy harm harsh harvest haste hatch hate haunt haven
hawk hay hazard head heal health heap hear hearse heart hearth heat heaven
heavy hedge heel height heir helicopter helm help hence herb herd
here heritage hero herself hesitate hexagon hiccup hide high highway hill
hinge hint hip hire history hitch hive hoard hobby hockey hoe hold hollow
holy homage honest honey honor hood hoof hook horizon horn horrid horse
host hostel hostile hotel hound house hover howl huge human humble humid
humour hunger hunt hurdle hurl hurry hurt husband hush husk hut hybrid hymn
icicle icon idea ideal idle idol ignite ignore iguana ill image imagine imitate
immense immerse immune impair impart impatient import impose impress
improve inch include income increase index indicate indict indoor indulge
infant infect infer infest inform inherit initial inject injure inland inlet
inner input inquire insect insert inside inspect inspire install instant
instead insure intact intake intense intent interact interest intern
interpret interrupt intimate into invade invalid invent invert invite invoke
involve iron irony island isle issue item ivory jacket jade jail jam jar
jasmine jaundice jaw jealous jelly jerk jest jet jetty jewel
jewellery jewelry jingle job jockey jolly jolt journey jovial joy joyful
judge jug juggle juice jumble jumbo jump jungle junior jury just jut keen
keep kennel kept kettle key kick kid kidney kind kindle king kiss kitchen
kite kitten knack knave knead knee kneel knew knife knight knit knob knock
knot know knowledge knuckle koel labour ladder ladle lady laid lake lamb
lamp lance land lane lantern lap lapse large lark laser latch late later
laugh launch laundry laurel lava lavish law lawn lawyer layer lazy lead
leaf league leak lean leap learn lease least leather leave lecture ledge
leech left leg legacy legal legend leisure lemon lend length lens lentil
less lesson lest letter lettuce level lever liar liberal lick lid life lift
light lighten like likely lilac lily limb lime limit limp line linen liner
link lion liquid liquor list listen litter little live lively liver lizard
llama load loaf loan lobby local locate lock locker locus locust lodge loft
logic lonely look loom loop loose loot lord lorry lose loss lot lotus loud
lounge louse love lovely lover lower loyal lucid luck luggage lukewarm lull
lumber lump lunar lunch lure lurch lush lustre luxury lymph lyric magnet
maiden mail main maize major make malaria male mall malt manage mane
mango manner manor mansion mantle manual manufacture manure many map maple
marble march margin marigold marine mark market marry marvel mask mason
mass master match mate material mathematics maths matter mattress mature
maximum mayor maze meadow meal mean meant measles measure meat medal meddle
media medic medical medium meek meet melon melt member memo memoir memory
menace mend mental menu mercy merge merit merry mesh mess metal meter
method metre micro microscope midday middle midnight midst might migrate
mild mile milk mill mimic mince mind mine mineral mingle minor minus
minute miracle mirror mirth misery miss missile mission mist mistake mister
mistress mix moan mobile mock mode model modem modest modify moist molar
mold moment monarchy money monitor monk monkey month mood moon moral mosque
mosquito moss motel mother motif motion motor motto mould mound mount
mourn mouse mouth movie mud muddy mule multiply murmur muscle museum music
must muster mute mutter mutton mutual muzzle myself mystery myth nail naive
naked name nap narrate narrow nasal nasty nation native naughty nausea
naval nave navy near neat nectar need needle neglect neigh neighbour nestle
nest nettle never new newly news next nibble nice niche nickel niece night
nightingale nimble nine nineteen ninety nip noble noise nominal nomad none
noodle noon normal north nose nostril notch note notice notion noun
nourish novel novice now nowhere nozzle numb number nurse nursery nut
nylon oak oar oasis oat oath obey object oblige oboe observe obtain obvious
occasion occupy occur ocean ochre octave odd odour offer office often oil
ointment old olive omit once onion only ooze open opera operate
opinion oppose optician option orange orbit orchard order organ origin
ornament orphan ostrich other otter ought ounce outer outline output oval
oven over overcoat overcome owl own owner ox oyster pace pack packet pact
pad paddle paddy page paid pail pain paint pair palace pale palm panel
panic pansy paper parade parcel pardon parent parish park parrot part
particle party pass passion past paste pastry patch patent path patio
patriotic patrol pattern pause pave paw pawn pay peace peach peacock peak
peal peanut pear pearl peasant pebble peck pedal peel peep peer pelt pen
penalty pencil pendant pendent penny people pepper perceive perch perfume
perhaps period perish perk perm permit persist person pest petal petition
petrol petticoat petty phase phone photo phrase piano pick pickle picnic
picture piece pier pierce piety pigeon pile pilgrim pill pillar pillow pilot
pin pinch pine pink pint pioneer pious pipe pirate pistol piston pity pizza
place plague plain plan plane planet plank plant plasma plaster plate
plateau platform plead pleasant please pleasure pleat pledge plenty plight
plod plot plough pluck plug plum plumber plume plump plunder plunge plural
plus pocket poem poet poetry poignant point poison polar pole polish polite
polite poll pollen pond ponder pony pool poor popcorn poppy popular porch
porch pose posh position possess possible post postage postal poster postman
potato potter pouch poultry pound pour poverty powder power practise
praise prank prawn pray preach precede precious precis precise
predict prefer prefix pregnant premium prepare present preserve
press pressure presume price prick pride priest primary prime prince
print prior prism prison private prize probe prod prodigal profuse
project prompt prone proof propel proper property prophet prose proud prove
proverb provide province provision prune psalm pub public pudding puddle
puff pull pulpit pulse pump punch punctual punish pupil puppet puppy
purchase pure purple purpose purse pursue push puzzle python quack quail
quake qualify quality quantity quarrel quart quartz queen quench
query quest question queue quick quiet quilt quire quirk quit quite quiz
quote rabbit rabies race rack racket radar radiate radio radish raft rag
rage raid rail rain rainbow rainy raise rake rally range rank rapid rare
rash rat rate rather ratio rattle raven reach react read ready realm reap
rear reason rebel recall receive recent recess recipe recite reckon
reclaim recline record recover recreation recur red redden redeem reduce
reed reef reel refer refine reflect reform refresh refuge refund refuse
regal regard regime region register regret regular rehearse reign rein
reject rejoice relate relax relay release relief relieve religion relish
reluctant rely remain remark remedy remember remind remit remnant remote
remove render renew rent repair repay repeat repel reply report repose
request rescue research resemble resent reserve reside resign resist
resist resolve resort resource respect respond rest restaurant restore
result resume retail retain retire retort retreat return reunion reveal
revel revenge revenue revere reverse review revise revive reward rheum
rhyme ribbon rice rich rid riddle ride ridge rifle right rigid rinse riot
ripen rise risk rival river rivet roar roast rob robe robin robot rock
rocket rod rode rogue role roll roman roof rook room roost root rope rose
rosy rot rotate rotten rouge rough round rouse route routine row royal rub
rubber rubbish ruby rudder rude rug ruin rule ruler rumour rural rush rust
rustic ruthless sack sacred sacrifice saddle sad safe saffron sag sage said
sail saint sake salad salary salmon salt salute same sample sand sandal
sandalwood sane sang sanitary sapphire sarcasm sari saree sash sat
satisfy sauce saucer savage save savour say scab scale scallop scalp
scanty scar scarce scare scarf scatter scene scent scheme scholar school
science scissors score scorn scout scrap scrape scratch scream screen screw
scribe scroll scrub scuba sculpt scum scurry seal seam search season seat
second secret section sector see seed seek seem seen seldom select self
sell senate send senior sense sentence sequel series serious sermon serve
service sesame seven severe sew shade shadow shaft shake shall shallow shame
shape share shark sharp shatter shave shawl she sheaf shear sheath shed sheen
sheep sheer sheet shelf shell shelter shepherd shift shine shiny ship shirt
shiver shock shoe shook shoot shop shore short shout shove show shower shred
shrewd shriek shrimp shrine shrink shrub shrug shudder shuffle shut shy sick
sickle side siege sieve sigh sight sign signal silent silk silly silver
similar simple since sincere sinew sing singer single sink sir siren sister
sit site six sixth sixty size skate sketch skill skin skip skirt skit sky
slab slack slain slam slang slant slap slate slaughter slave slay sleep
sleet sleeve slice slide slight slim sling slip slipper slope slot sloth
slow slug slum slump sly smack small smart smell smile smith smoke smooth
snack snail snake snap snare snarl snatch sneak sneer sneeze sniff snipe
snooze snore snow snug soak soap soar sober soccer social society sock soda
sofa soft soil solar soldier sole solemn solicit solid solo solve sombre
son song soothe sore sorrow sorry sort soul sound soup sour source south
souvenir sovereign space spade span spare spark sparrow speak spear special
species specific speech speed spell spend sphere spice spider spill spin
spiral spirit spite splash spleen splendid split spoil spoke sponge
spoon sport spot spouse sprain sprawl spray spread spring sprinkle sprite
sprout spruce spur square squash squeak squeal squeeze stable stack stadium
staff stag stage stagger stain stair stake stale stalk stall stammer stamp
stand stare startle start state station stay steady steak steal steam steel
steep steer stem stench step stern stew stick sticky stiff still sting stir
stitch stock stoic stole stolen stomach stone stood stool stoop stop store
storm story stove straight strain strange strap straw stray stream street
strength stress stretch strict stride strike string stripe strive stroke
stroll strong struggle student study stuff stumble stump stunned stupid
sturdy style subject submit subtle subtract suburb succeed success such
suck sudden suffer suffice suffix sugar suit suite sultry sum summer summit
summon sun sundry sunk super superb supper supple supply support suppose
suppress supreme sure surface surge surgeon surname surpass surprise
surrender surround survey survive suspect suspend suspicion swallow swamp
swan swap swarm sway swear sweat sweater sweep sweet swell swift swim swing
switch sword symbol sympathy symphony syrup table tablet tack tackle tact
tag tail tailor take tale talent talk tall tame tan tang tank tap tape tar
target tariff task taste taught tavern tawny teach team tease teeth tell
temper temple tempt ten tenant tend tender tendon tenet tennis tenor tense
tent tenth term terrace terrible test text thank that thaw their theme then
theory there thermal these thick thief thieve thin thing think third thirst
thirteen thirty thorn those though thought thousand thrash thread threat
three thresh threw thrill thrive throat throb throe throne throng throw
thrust thumb thunder tick ticket tidal tide tidy tiger tight till timber
time tin tinkle tiny tired tissue title to toad toast today toe together
toil toilet token told toll tomato tomb tomorrow ton tone tongs tongue
tonic tonight too took tool tooth top topic torch torment torrent tortoise
total touch tough tour tourist towel tower town trace track tract trade
traffic tragic trail train trait tramp trample tranquil transact transfer
transform transit translate trap trash travel tray tread treasure treat treaty
tree trek tremble trench trend trial tribe trick trickle trim trip triumph
trivial troop trouble trough trout trowel truant truce truck true trumpet
trunk trust truth try tub tuck tug tulip tumble tumour tumor tuna tune
tunnel turban turbine turkey turmoil turn turtle tutor twelve twenty twice
twig twilight twin twist twitch type typhoid tyrant tyre ugly ulcer ultra
umber umbrella umpire unable uncle uncover under undergo underlie
underline underneath undo undone unfold union unique unit
unite unity universe unload unlock unlucky unpack unrest until untrue up
uphold uphill upper upright uproar upset urban urge urgent urine urn use
usual usurp utter uttermost vacant vague vain vale valid valley valour
value van vanish vapour variety various vary vase vast vault vaunt veal
veg veil vein velvet vendor venom vent venue verb verdict verge verse
versus very vessel vest veto vex via vibrate vice victory vie view vigil
vigor vigour village villain vine vinegar violate violin viper virgin
virtue virus visa visage visit visor vista vital vivid vocab vocal
vociferous vodka vogue voice void volcano volt volume volunteer voyage
vulgar vulture wafer wag wagon wail waist wait wake walk wall wallet
wander wane want war warble ward wardrobe warm warn warp warrant wart
wash wasp waste watch water watt wave wax way weak wealth weapon wear
weary weather weave web wedding wedge week weep weigh weight weird welcome
weld well west whale wharf what wheat wheel whelp when whence where
whether which whiff while whim whimper whilst whine whip whirl whisk
whisper whistle white whole wholesome whom whose why wick wicked wide widow
width wife wig wild will willow wilt win wince winch wind window wine wing
wink winner winter wipe wire wisdom wise wish wit with withdraw wither
within without witness wizard wobble wolf woman women wonder wood wool
word wore work world worm worry worth would wound weave woven wrap wrath
wreath wreck wrench wrest wrestle wretch wrick wrist write writer writhe
wrong wrote yacht yak yam yap yard yarn yawn year yearn yeast yell yellow
yelp yield yoke yolk young your youth zebra zenith zephyr zero zest zigzag
zinc zip zone zoo
""".split()

# Tier 2: academic writing - essay parts, argument words, formal vocabulary.
_TIER_2 = """
abstract academic accent accept access accord account achieve acquaint
acquire across actor adapt addendum address adept adhere adjacent adjust
administer admit adopt adore advance adverse advice advise advocate affair
affect affirm agenda aggregate agony aid aim alarm alert algebra alien align
alike alive allege allocate allow alloy allude alone along aloud alter
alternate although altitude altruism amass amaze ambiguous ambition amend
amendment among amount ample amuse analyse analysis analytic analyze angel
anger angle animate annex annotate announce annoy annual annul anomaly
answer anticipate antic apex ape append appendix applaud apply appoint
apposite appraise appreciate apprehend approach approve apt aptly area argue
arise arm array arrest arrogant article ascend ascertain aspect aspire
assail assault assemble assert assess asset assign assimilate assist associate
assume assure astound astray asylum attain attempt attend attention
attitude attract attribute audience audit author authority autumn avail
avarice avert avoid await award aware awe awful axiom axis bacon badge
balance balk ban banish bank banner bar bare bargain barrier base basin
basis batch bawl bear beast beat behalf behave belief bell belong below
bench bend beneath benefit berth beside best bestow betray bewail beyond
bias bible bibliography bid bill biology bisect bitter bizarre blame blank
blast blaze bleed blend bless blind bliss block bloom blossom blot blow
bluff blunt blurt blush board boast boastful boat bode body boil bold bolster
bolt bond bone bonus book boost booth boot border bore borrow bosom boss
botany bottle bound bounty bouquet bow bowel bowl box boycott brace brag
braid brain brake branch brand brass brave brawl breach bread breadth break
breakdown breakfast breast breath breathe breeze bribe brick bridal bridge
brief bright brilliant brisk broad broadcast brood brook broom brother
brought brow brown browse bruise brush brutal budget buffet build bulk
bullet bulletin bump bunch bundle burden bureau burgeon burglar burial burn
burnish burst bury bus bush bust bustle busy butler butter button buyer
bypass bystander cab cabinet cable cactus cadence cage cajole cake calamitous
calculable calculate calendar calibre caliber call callous calm calumny camel
came camera camp campaign campus canal cancel candid candle candid candidly
canny canvas cap capable capacious capacity capital capitulate caprice
captain caption captivate capture carbon card career caress cargo caricature
carnage carol carpet carriage carry carve cascade case cash caste castle
casual casualty catalogue catalog catch catchy category cater cattle cause
caustic caution cautious cease cease ceaseless cedar ceiling celebrate
censor censure census century cereal ceremony certain certify cessation
chafe chaff chain chair chalk challenge chamber champion chance change
channel chant chaos chap chapter character charge charity charm chart chase
chasm chaste chat chatter cheap cheat check cheer cheese chemist cherish
chess chest chew chick chicken chide chief child chill chime chimney chirp
chisel chivalry choice choir choke choler choose chop chord chorus chose
chronic chronicle chuckle church churn cider cinema cipher circle
circuit cite citizen civic civil claim clam clamour clamp clan clap clarify
clash clasp class classic classify clause claw clay clean cleanse clear
cleave cleft clerk clever click client cliff climate climb clinic clip clique
cloak clock clog clone close closet cloth clothe cloud clown club clue clumsy
cluster clutch clutter coach coalesce coarse coast coat coax cobra cockroach
cocoa code codify coerce coexist coffee cogent coil coin coincide cold
collaborate collapse collar colleague collect collide colony colossal column
combat combine comedy comely comfort comic comma command commence commend
comment commerce commit committee common commotion
commute compact companion company compare compass compatible compel compendium
compensate compete competent compile complacent complain complaint complete
complex complexion complicate comply component compose composite compost
composure compound comprehend compress comprise compromise compulsion
compute comrade conceal concede conceit conceive concentrate concept concern
concert concede concave conclude concrete concur condemn condense condescend
condiment condition condole condone conduct confer confess confide confident
confine confirm conflict conform confront confuse confute congeal congenial
congest congratulate congregate congress congruent conjure connect connive
connoisseur conquer conscience conscious consecrate consent conserve consider
consign consist console consolidate consonant consort conspire
constant constrain construct construe consul consult consume contact
contain contemplate contempt contend content contest context continent
continue continuum contract contradict contrary contrast convene converge
converse convert convex convey convict convince convoy convulse cook cool
copious copy coral cord cordial core cork corn corner corporate corpse
corpus correct correlate corridor corrode corrupt corsair cost costume
cottage cotton couch cough council counsel count counter countless country
coup couple courage course court courteous cousin covenant cover covet cow
cower crack cradle craft crag crane crash crate crave crawl crayon craze
crazy crease create credo credit credo creek creep cremate crest crew cricket
cripple crisis crisp criterion critic crocodile crony crop cross crotchety
crowd crown crude cruel cruise crumb crush crust crutch crux cry cryptic
crystal cub cube culprit cultivate culture cumber cumbersome cumulate
cunning cup cupboard curb cure curfew curious curl current curriculum curse
cursory curtain curve cushion custard custom customer cut cycle cyclic cyclone
cynic daily dainty dais dairy daisy dally damp dampen dance dandle
dandruff danger dangle dapple dare dark darken dart dash data date daub
daughter daunt dawn day daylight daze dazzle dead deadline deadly deaf deal
dean dear dearth death debacle debate debit debris debut decade decay decease
deceit deceive decent decentralise decentralize decide decimal
decimate decipher decision decisive deck declare decline decode decor
decorate decorum decrease decree dedicate deduce deed deem deep deer deface
defame default defeat defect defend defer deference defiant define definite
deflect deform defraud defray deft defunct defy degrade degree deign deity
delay delegate delete deliberate delicate delight delineate delinquent
delirious deliver delta delude deluge delve demand demarcate demeanour
demeanor demolish demon demonstrate demure dense dent dental deny depart
depend depict deplete deplore deploy deport depose deposit depot deprave
depress deprive depth depute deputy deride derive derogate descend
describe descry desert deserve design designate desire desirous desk desolate
despair despatch despise despite despoil dessert destine destiny destitute
destroy detach detail detain detect deter detergent deteriorate determine
detest detonate detour detract develop device devil devise devoid devote
devotee devour dew dexterity diabetes diagnose diagram dial dialect dialogue
dice dictate dictum did die differ digest dignity digress dilute diligent
dim dimension diminish dine dinner dip dire direct dirty disable disagree
disappear disarm disaster disband disbelief discern discharge disciple
discipline disclaim disclose discord discount discourage discourse discover
discreet discrepant discrete discuss disdain disease disguise disgust dish
dishonest disk dismal dismantle dismay dismiss disorder disown disparage
disparate dispatch dispel dispense disperse displace display displease
dispose dispute disrupt dissect dissent dissertation dissolve distant distil
distill distinct distinguish distort distract distress distribute district
distrust disturb disuse ditch ditto diverge diverse divert divide divine
dizzy dizzy doctor doctrine dodge does dog dogged dogma doldrums doll
dolphin domain domesticate donate donkey doom dormant dossier dot dote double
doubt dough dove down dowdy dowry doze dozen draft drag drain drama drape
drastic draw drawer dread dream dreary dredge dress dried drift drill drink
drip drive drizzle drone droop drop drought drove drown drudge drug drunk
dry duck duct due duel dug dull dumb dummy dump dune dung duo dupe during
dusk dust dutiful duty dwarf dwell dwindle dye dynamic eager eagle ear early
earn earnest earth earthquake ease easel east easy ebb ebony echo eclipse
ecology edict edifice edit educate eerie effect effigy effort effulgent egg
eight eighteen eighth eighty either eject elbow elder elect elegy element
elevate eleven elicit elite elixir ellipse else elusive email embark embarrass
embassy embed ember emblem embody embrace embroider emerge emergency emit
emotion employ empty enable enact enamel enamour encamp encircle encore
enclose encomium encore encounter encourage encroach endless endorse endure
enemy enforce engage engine engrave engulf enjoy enlarge enlighten enlist
enmity ennui enormous enough enquire enrich enrol enroll ensue ensure entail
enter enterprise entertain enthral entice entire entitle entity entrance
entrap entreat entry enumerate enunciate envelope enviable envy enzyme epic
epidemic epilepsy episode epitaph epithet epitome epoch equal equanimity
equation equator equip era erase erect erode err errand error erupt escape
essay essence essential estate esteem estimate eternal ethic ethnic evade
evaporate even evening event evict evil evoke evolve exact exalt exam
examine excavate exceed excel except excess exchange excise excite exclaim
exclude excrete excursion excuse exempt exert exile exist exit exotic expand
expanse expect expedite expense expert expire explain expletive explicit
explode exploit explore exponent export expose expound express
exquisite extend extent extenuate exterior extinct extol extort extra extract
extraneous extreme eyebrow fabric fable fabricate facet facetious facile
facilitate fact faction factor factory faculty fade fail faint fair fairy
faith fake fall fallacy false falter fame familiar family famine famous fan
fanatic fancy far farce fare farm fascinate fashion fast fasten fatal fate
father fathom fatigue fault favour favorite favouritism
feast feat feather feature February fecund fee feeble feed feign feint fell
fellow felt female fence fend ferment fern ferret ferry fertile fertilise
fertilize fervent fervour fester fetch fetid feud fever few fibre fiction
fiddle fidelity field fiend fierce fiery fifteen fifth fifty fig fight figure
filament file filial fill fillet film filter fin final finance find fine
finger finish finite fir fire firm first fiscal fish fissure fit fix fixture
flag flagrant flair flame flank flap flare flash flask flat flatter flavour
flaw flea flee fleet flesh flew flex flick flight flimsy flinch fling flint
float flock flood floor flop flora floral flourish flow flower fluid flush
flute flutter flux focus fodder foe fog foil foist fold folk follow folly
fond food fool foot force fore forebear forecast forego foreground forehead
foreign foreman foremost forenoon foresee forest foreshadow forestall forge
forget forgive forgo fork forlorn form formal format former formidable
forsake fort forte forth fortify fortnight forty forum forward fossil foster
foul found founder four fourteen fourth fowl fox fraction fracture fragile
fragrant frail frame frank frantic fraud fraught fray freak freckle free
freedom freeze freight frenzy frequent fresh fret friar friction Friday
friend fright frighten frigid fringe frock frog frolic frost frown frowned
frozen frugal fruit frustrate fry fudge fuel fulfil fulfill full fulminate
fumble fume fun function fund fundamental funeral fungus funnel funny fur
furious furnish furniture furore further furtive fury fuse fuss fusty future
gadget gain gait gala galaxy gallant gallery gallon gallop galore gang gap
garage garb garden gargantuan garlic garment garner garter gas gash gasp
gate gather gauge gaunt gaze gear gem gender gene genealogy general generate
generic generous genesis genre genteel gentle genuine genus germ germinate
giant gibber gibe giddy gift gig gigantic ginger giraffe gird girl girth
gist give glacier glad glance gland glare glass gleam glean glide glimpse
glitter gloat globe gloom glory gloss glossary glove glow
glower glue glut gnarled gnat gnaw goad goal goat gobble goes gold golden
good goods gorge gorgeous gossip gouge gourd govern gown grab grace gracious
grade gradual grain gram grammar grand grandeur grant grape graph graphic
grasp grass grateful gratify gratis grave gravel gravity graze grease great
greed green greet grief grievance grill grim grime grin grind grip gripe
groan grocer groom groove grope gross grotesque ground group grouse grove
growl grown growth grudge gruel gruesome gruff grumble grunt guard guardian
guess guest guide guild guile guilt guise guitar gulf gull gully gum gusto
gust gut guy guzzle habit hackneyed hail hair half hall hallmark halt halve
ham hamlet hammer hamper hand handful handicap handle handsome handy hang
hanker hapless happen happy harangue harass harbour harbor
hard harden hardy harm harmony harness harp harsh harvest haste hasten hatch
hate haughty haunt haven havoc hawk hay hazard head heady heal health heap
hear hearken hearse heart hearth hearty heat heath heathen heave heaven heavy
heckle hedge heed heel height heinous heir helicopter helm help hence herald
herb herd here heritage hero heroine hesitate hexagon heyday hibernate hiccup
hide hideous high highway hilarity hill hinder hinge hint hip hire hiss
history hitch hive hoard hoarse hoary hobby hockey hoe hoist hold hole
holiday hollow holy homage honest honey honor hood hoof hook hoot horizon
horn horrid horror horse hospitable host hostel hostile hotel hound house
hover howl hub huge hull hum human humane humble humid humiliate humour
hump hunch hunger hunk hunt hurdle hurl hurrah hurry hurt husband hush husk
hut hybrid hymn hyperbole hypocrisy hysteria icicle icon idea ideal idle
idol idyll ignite ignoble ignominy ignore iguana illumine illusion
illustrate image imagine imitate immaculate immense immerse immigrate
imminent immune impair impart impartial impatient impeach impede impel
impending impenetrable imperil imperial imperious impetuous impinge impious
implacable implore imply import important impose impostor impress impress
imprint improve improvident impulse impunity inane inanimate inaugurate inborn
incense incessant inch incidence incisive incite incline include income
increase incredible index indicate indict indigent indoor induce
indulge industry infant infantile infect infer inferno infest infidel infinite
infirm infix inflame inflate inflect inflict influx inform informer ingenious
ingrate inhabit inhale inherit inhibit initial initiate inject injure inland
inlet inly inmate inner innocent input inquire inquiry inroad insect insert
inside insight insist inspect inspire install instance instant instead instep
instigate instil insult intact intake integer intense intent interact intercept
interest interim interior interject interlude intern interpret interrogate
interrupt intersect intimate intimidate into intrigue introduce introvert
invade invalid invaluable invariably invent inventory invert invest invite
invoke involve inward irate irony irons irk irksome island isle issue item
ivory jab jabber jack jackal jacket jade jaded jagged jail jam jamboree jar
jargon jasmine jaundice jaunty jaw jealous jeer jelly jerk jest jet jetty
jewel jewellery jingle job jockey jocular
jolly jolt jostle journey jovial joy joyful jubilant judge judicious jug
juggle juice jumble jumbo jump jungle junior junk junta jury just justice
justify jut juvenile juxtapose keen keep keepsake kennel kept kernel kettle
key kick kid kidney kill kin kind kindle kindred king kiosk kiss kitchen kite
kitten knack knave knead knee kneel knew knife knight knit knob knock knot
know knowledge knuckle koel label laborious labour labyrinth lack laconic
ladder laden ladle lady laid lake lamb lame lamp lance land lane languid
languish lantern lap lapse large largess lark laser lash latch late latent
later lateral laugh launch laundry laurel lava lavish law lawful lawn lawyer
lax layer lazy lead leaf league leak lean leap learn lease least leather
leave leaven lecture ledger leech leer left leg legacy legal legend legible
legion leisure lemon lend length lenient lens lentil less lessen lesson lest
lethal letter lettuce level lever levy liar libel liberal liberate lick lid
lie lien lieu life lift light lighten like likely lilac lily limb limber lime
limit limp line lineage linen liner linger link lion liquid liquidate liquor
lisp list listen lithe litter little live lively liver lizard llama load loaf
loan loathe lobby local locale locate lock locker locus locust lodge loft
logic loiter lonely look loom loop loose loot lop loquacious lord lorry lose
loss lot lotus loud lounge louse love lovely lover low lower loyal lucid luck
lucky lucre luggage lukewarm lull lumber luminary lump lunar lunch lurch lure
lurid lurk lush lust lustre luxury lymph lyric lyrical macabre machine madden
magic magnanimous magnet maiden mail maim main maize major make malaria malice
malign mall malt maltreat manage mandate mane manful mango mania manifest
manly manner manor mansion mantle manual manufacture manure many map maple
mar marathon maraud marble march margin marigold marine marital mark market
maroon marry marvel mask mason mass massacre master masterful match mate
material matron matter mattress mature mature maxim maximum mayor maze meadow
meagre meal mean meander meant measles measure meat medal meddle
mediate medic medical medieval mediocre meditate medium meek meet melancholy
meld melee melon melt member memoir memory menace mend mendacious mental menu
mercantile mercy mere merge merit merry mesh mess message metal metamorphose
metaphor meteor method metre metric micro microscope midday middle midnight
midst might migrate mild mile milk mill mimic mince mind mine mineral mingle
miniature minor minus minute miracle mirage mire mirror mirth misery misgiving
miss missile mission mist mistake mister mistress mitigate mix moan mob mobile
mock mode model modem moderate modest modify moist molar mold moment monarchy
money monitor monk monkey monopoly month mood moon moral morale morbid morose
mortal mortar mosaic mosquito moss motel motif motion motivate motor motto
mould mound mount mourn mouse mouth move movie muffle mug multiply murmur
muscle museum muse music must muster mute mutilate mutiny mutter mutual muzzle
myriad myself mystery myth nab nail naive naked name nap narrate narrow nasal
nasty nation native natter naughty nausea naval nave navy near neat nebula
nectar need needle nefarious neglect negligee neigh neighbour neither neologism
nerve nest nettle never new news next nib nicety niche nickel niece niggard
night nightingale nimble nine nineteen ninety nip noble nocturnal noise
nominal nomad none nonplus noodle noon norm normal north nose nostril notch
notion noun nourish novel novice now nowhere nozzle nuance numb number nurse
nursery nurture nut nylon oak oar oath obey obeisance object oblige oblique
obliterate oblivion obnoxious oboe observe obsess obtain obtuse obvious
occasion occult occupy occur ocean octagon octave odd ode odious odour offer
office often oil ointment old olive omen omit omnipotent once one onion only
onslaught ooze opaque open opera operate opinion oppose opportune oppose option
oracle oral orange orbit orchard order organ orient origin ornament ornate
orphan orthodox oscillate osseous ostrich other otter ought ounce oust outer
outfit outlaw outline output outrage oval ovation oven over overcoat overcome
overflow owl own owner ox oxide oyster pace pack packet pact pad paddle
paddy page pageant paid pail pain paint pair palace palatable pale pall pallid
palm palpable palsy panel pang panic panorama pansy pant paper parade paradigm
parcel pardon parent parish parity park parody parole parrot parry parse part
partake partial particle particular party pass passage passion passive past
paste pastel pastry patch patent path pathos patio patriotic patrol patron
pattern pause pave paw pawn pay pea peace peach peacock peak peal peanut pear
pearl peasant pebble peck pedal peel peep peer peerless pelt pen penalty
pencil pendent penny pension people pepper perceive percent perch perfume
perhaps peril period perish perjure perk perm permanent permeate permit
pernicious perpetrate perpetual perplex persecute persevere persist person
personable personify perspective pertain pertinent perturb peruse
pest pester petal petition petrify petrol petticoat petty petulant phase phone
phrase physical piano pick pickle picnic picture piece pier pierce piety pigeon
pigment pile pilgrim pill pillar pillow pilot pin pinch pine pink pinnacle pint
pioneer pious pipe piquant pirate pistol piston pity pivot pizza placard place
placate plague plain plaint plant plantplate plateau platform plaudit plead
pleasant please pleasure pleat pledge plenty plight plod plot plough pluck plug
plum plumb plumber plume plump plunder plunge plural plus poach pocket podium
poem poet poetry poignant point poise poison polar pole politic polite poll
pollen pollute ponder pony pool poor poppy popular populace porch pore porous
port portable portal portend pose posh posit position possess possible post
postage poster postman postpone postulate potato potent pouch poultry pound
pour poverty powder power practise praise prance prank prawn pray preacher
precarious precede precedent precept precious precise precis precision preclude
predicament predict prefix pregnant prelude premature premier premise premium
prepare present preserve preside press pressure presume pretend pretext pretty
prevail prevent preview prey price prick pride priest primal primary prime
primeval prince principal principle print prior prism prison pristine private
privy prize probe probity problem proceed process proclaim procure prod prodigal
prodigy produce product profane profess proffer profile profit profuse project
prolific prompt prone proof propagate propel proper property prophecy prophet
proponent prose prosecute prosody prospect prosper prove proverb provide
province provision provoke prowess prune pry psalm pub public publish pudding
puddle puff pugilism pull pulpit pulse pump punch punctual pundit punish pupil
puppet puppy purchase pure purge purple purpose purse pursue push puzzle python
quack quaff quail quake qualify quality qualm quantity quarrel quart quartz
quash queen quell quench query quest question queue quibble quick quiet quilt
quintessence quire quirk quit quite quiz quote quoth rabbit rabbi race
rack racket radar radiant radiate radical radio radish raft rag rage raid rail
railway rain rainbow rainy raise rake rally ramp rampant range rank ransack
rapid rapport rare rash rat rate rather ratify ratio rattle raven ravenous
ravish raw reach react read ready realm reap rear reason reassure rebel recall
recant receive recent recess recipe recite reckless reckon reclaim recline
recluse record recount recover recreation recruit red redden redeem redeemable
redress reduce redundant reed reef reel refer referee refine reflect reform
refrain refresh refuge refund refuse refute regal regard regime regiment
region register regret regular rehearse reign rein reinforce reject rejoice
relapse relate relax relay release relent relief relieve religion relinquish
relish reluctant rely remain remark remedy remember remind remit remnant
remorse remote remove render rendezvous renew renounce renovate rent repair
repartee repay repeal repeat repel repent reply report repose reprehend
represent repress reprieve reprimand reprisal reproach reprove reptile repulse
request requiem require rescue research resemble resent reserve reside residue
resign resist resist resolve resonant resort resource respect respite respond
rest restive restore restrain result resume retail retain retch retinue retire
retort retrace retract retreat retribution retrieve retrograde return reunion
reveal revel revenge revenue revere reverie reverse revert review revise revive
revoke reward rhapsody rhetoric rheum rhyme rhythm ribbon rice rich rid riddle
ride ridge rifle rift right rigid rigor rinse riot ripen rise risk rite rival
river rivet roam roar roast rob robe robin robot robust rock rocket rod rode
rogue role roll roman romance romp roof rook room roost root rope rosary rose
rosy rot rotate rotten rouge rough round rouse rout route routine rove row
royal rub rubber rubbish ruby rudder ruddy rude rug ruin rule ruler rumour
rural ruse rush rust rustic ruthless sabbath sabotage sack sacred sacrifice
saddle sad safe saffron sag sage said sail saint sake salad salary salmon
salutary salute salvage salve same sample sanctify sanction sanctuary sand
sandal sandalwood sane sang sanguine sanitary sapphire sarcasm sash sat
satanic satchel satiate satire satisfy saturate sauce saucer saunter savage
save savour savoury say scab scaffold scale scallop scalp scamp scan scant
scanty scar scarce scare scarf scatter scene scent scheme scholar school
science scissor scoff scold scope scorch score scorn scour scout scowl scrap
scrape scratch scrawl scream screen screw scribe scribble scroll scrub sculpt
scum scurry scuttle seal seam search season seat second secret
sect section secure sector see seed seek seem seen seep seethe seldom select
self selfish sell semblance senate send senior sense sensuous sentence
sentinel sequel sequence serene series serious sermon serve service servile
sesame session seven sever several severe sew shade shadow shaft shake shall
shallow shame shape share shark sharp shatter shave shawl she sheaf shear
sheath shed sheen sheep sheer sheet shelf shell shelter shelve shepherd shift
shine shiny ship shirk shirt shiver shoal shock shoe shook shoot shop shore
short shortage shout shove show shower shred shrew shrewd shriek shrimp shrine
shrink shrub shrug shudder shuffle shun shut shuttle shy sick sickle side
sidle siege sieve sigh sight sign signal signature signify silent silhouette
silk silly silver similar simile simple simulate since sincere sinew sing
singer single singular sinister sink sip sir siren sister sit site six sixth
sixty size skate skeleton sketch skill skin skip skirmish skirt skit sky slab
slack slain slake slam slander slang slant slap slash slate slaughter slave
slay sleep sleet sleeve sleight slice slide slight slim sling slink slip slipper
slope slot sloth slouch slow slug slum slump slur sly smack small smart smash
smell smile smith smite smoke smooth smother smug smuggle snack snail snake
snap snare snarl snatch sneak sneer sneeze sniff snipe snooze snore snort snow
snug soak soap soar sober soccer social society sock socket soda sofa soft
soften soil sojourn solar soldier sole solemn solicit solid solo soluble solve
sombre somnambulist son sonnet soothe sore sorrow sorry sort soul sound soup
sour source south sovereign space spade span spangle spare spark sparrow
sparse spasm speak spear special species specific specimen specious speck
speech speed spell spend sphere spice spider spill spin spindle spiral spirit
spite splash spleen splendid splendour split spoil spoke sponge sponsor spoke
spoon sport spot spouse sprain sprawl spray spread spring sprinkle sprite
sprout spruce spur spurious square squash squeak squeal squeeze stab stable
stack stadium staff stag stage stagger stain stair stake stale stalk stall
stammer stamp stance stand stanza star starch stare stark start startle state
stately static station statue stature stay steadfast steady steak steal stealth
steam steel steep steer stellar stem stench stencil step stern stew stick
sticky stiff stifle stigma still still stimulate sting stingy stir stitch stoic
stole stolen stomach stone stood stool stoop stop storage store storm story
stout stove straight strain strait strange strap stratagem straw stray streak
stream street strength stress stretch strife strike string stringent strip
stripe strive stroke stroll strong structure struggle student study stuff
stumble stump stun stunned stupid sturdy style suave subject subjugate sublime
submit subordinate subscribe subside subsidy subsist subtle subtract suburb
succeed success succour such suck sudden sue suffer suffice suffix suffocate
sugar suggest suit suite sulky sullen sultry sum summary summer summit summon
sundry sunk super superb supine supper supple supply support suppose suppress
supreme sure surface surge surgeon surname surpass surplus surprise
surrender surround survey survive suspect suspend suspense suspicion sustain
swallow swamp swan swap swarm sway swear sweat sweater sweep sweet swell
swelter swift swim swing switch swoon sword symbol symmetric sympathy symphony
syrup system table tablet tack tackle tact tactic tag tail tailor taint take
tale talent talk tall tally tame tan tang tangible tank tantamount tap tape
taper tar tardy target tariff tarnish task taste taught taunt taut tavern tawny
teach team tease teem teeth tell temper temperate tempest temple tempt ten
tenable tenant tend tender tendon tenet tenor tense tent tenth tenuous term
terrace terrain terrible terror test text thank thaw their theme then theologian
theory there thermal these thick thief thieve thin thing think third thirst
thirteen thirty thong thorn those though thought thousand thrall thrash thread
threat three thresh threw thrift thrill thrive throat throb throe throne throng
throw thrust thumb thunder tick ticket tidal tide tidy tie tiger tight till
timber timbre time timid tin tinkle tiny tip tipsy tired tissue title to toad
toast today toe together toil token told tolerate toll tomb tomorrow ton tone
tongs tongue tonic tonight too took tool tooth top topic torch torment torrent
tortoise total totter touch tough tour tourist tout towel tower town trace track
tract trade traffic tragic trail train trait tramp trample tranquil transact
transcend transfer transform transit translate translucent trap trash travel
tray tread treasure treat treaty tree trek tremble tremor trench trend
trepidation trespass trial tribe tribute trick trickle trim trinity trip tripe
triumph trivial troop trope trophy trouble trough truant truce truck true
trumpet truncate trunk truss trust truth try tub tuck tug tulip tumble tumour
tumor tuna tune tunnel turban turbine turbulent turkey turmoil turn turtle
tutor twelve twenty twice twig twilight twin twine twist twitch type typhoid
typhoon tyrant tyre ugly ulcer ultimate umber umbrella umpire unable uncle
uncouth uncover under underdog undergo underlie underline underneath undo
undone undulate unfold unison unit unite unity universal universe unkempt
unlike unload unlock unlucky unpack unravel unrest until unwieldy up uphold
upholstery upkeep uplift upper upright uprising uproar upset urban urge urgent
use usual usurp usury utter utmost utter vacant vacillate vague vain vale
valiant valid valise valley valour value vamoose van vandal vanish vanity
vanquish vapour variety various vary vase vast vault vaunt veal veil vein
velvet vendor venal vendetta venom vent venue verb verbal verdict verge verify
versatile verse versus very vesper vessel vest veto vex via viable vibrate
vice victory vie view vigil vigour vile villain vindicate vine vinegar violate
violent violet violin viper virgin virtue virtuoso virus visa visage visit
visor vista vital vivid vocab vocal vocation vogue voice void volatile volcano
volt volume voluminous volunteer voracious voyage vulgar vulnerable vulture
waffle waft wag wage wagon wail waist wait waive wake walk wall wallet walnut
walrus waltz wan wand wander wane want war warble ward wardrobe ware warfare
warm warn warp warrant wart wary wash wasp waste watch water watt wattle wave
wax way waylay weak weaken wealth weapon wear weary weather weave web wed
wedding wedge week weep weigh weight weird welcome weld well welter west whale
wharf what wheat wheel whelp when whence where whether which whiff while whim
whimper whine whip whirl whisk whisper whistle white whole wholesome whom
whose why wick wicked wide widow width wield wife wig wild will willow wilt
win wince winch wind window wine wing wink winner winter wipe wire wisdom wise
wish wit witch with withdraw wither within without withstand witness wizard
wobble woe wolf woman women wonder wont wood wool word wore work world worm
worn worry worth would wound weave woven wrap wrath wreath wreck wrench wrest
wrestle wretch wrist write writer writhe wrong wrote yacht yard yarn yawn
year yearn yeast yell yellow yelp yield yoke yolk young your youth yowl zebra
zenith zephyr zero zest zigzag zinc zip zone zoo
""".split()

# Tier 3a: science, technology, school subjects and lab words.
_TIER_3A = """
absorb abstract acid acoustics adapt adsorb airfoil airy algebra
algorithm alien alloy alpha altitude amber amoeba ampere amplify amplitude
anaemia anemia angle animal antenna anther antibiotic antibody
anvil aorta apparatus appendage apply approximate aquatic arc
area argue arithmetic armour artery aspect asteroid asthma atlas
atom atomic attract axis axle bacillus bacteria balance barometer base
basin battery beam beaker behave bellows belt bench beta bevel bias
bile biology biplane bird bitter black blast blink block blood bloom blot
blue boil bold bolt bond bone botany bottle bound brain brass break breed
breeze brick bridge brine bronze bubble bud bulb bulk burn button buzzer
bypass cable cactus calibrate calliper caliper calorie camera canal cancer
candle carbon carburettor care carrier cartilage cascade cast catalyst cathode
cavity cell cement centre chain chalk chamber change channel charge chart
chasm chassis cheat check chemist chemistry chill chip chisel chord
chrome chuck circuit cistern cite claim clamp clasp class classify
claw clay clean clear cleave cliff climate climb clinic clip clone cloud
cluster clutch coach coal coarse coast cobweb code coil coin cold collar
collect college collide colony column comb combine comet comma command
common compact compass compete compile complement complex compost compound
compute concave condense conduct cone confer conifer console constant
constrain construct contact contain continent contour control convex convey
cool copious copper copy coral cord core cork corn corona corpse corpus
cortex count couple court covalent cover crane crank crater craze
creek creep crest cricket crisis crisp crop cross crude cruise crust crystal
cube current curve cushion cycle cyclone cylinder damp data datum
decay decibel decimal decode deduce deduct deed deep define deflect degree
dense density dent depth derby derive descend describe desert design detail
detect develop device dew diagram dial diameter diamond diaphragm dice
diesel diet digit dilute dim diode dip direct disc discharge disco
discover discuss disease disk dissect distant distil distill distinct ditto
diverse divert divide dizzy doctor domain donate door double doubt download
draft drag drain drama drastic drawer dream dress drift drill drink drip
drive drone droop drop drought drown drum dry duct dune dwarf dye dynamo
eager eagle ear earth earthquake eclipse ecology eddy edge effect effort egg
elastic elbow elder electric electron element elevate eleven ellipse embryo
emit encode energy engage engine engrave enjoy enlarge enrol enter
entity entry envelope enzyme epic equal equation equator era erupt escape
essay essential estate ether ethic evaporate even evening event every exact exam
examine excavate exceed excel excess exchange excite excrete exercise exert
exhaust exhibit exist exit exotic expand expanse expect experiment expert
expire explain expletive explicit explode exploit explore exponent export expose
express extend extent extinct extra extract extreme eyeball fabric facet fact
factor factory fade fan fatal fathom fatigue fauna feather feature feign fell
ferment fern ferret fertile fever fibre fiction field filament file fill filter
fin final finch find fine finger finish fir fire firm first fiscal fish fissure
fix fixture flag flame flask flat flaw flea flee fleet flesh flex flick flight
flint float flock flood floor flora flour flow flower fluid flush flux focus
fog foil fold force forecast forest forge fork form formula fossil found founder
fraction frame frequent fresh friction frost fuel fulcrum fume fungus funnel fur
furnace fuse fuzzy gadget gain galaxy gallop galvanise galvanize gamma gap
garage gas gasket gauge gear gem gene general generate generic genius genre
germ germinate giant gibber giga giraffe glacier gland glass gleam glide
global globe gloss glove glow glue glyph gnat gnaw goad goal goat gold golden
goods gorge gouge govern grab grade gradient graft grain gram grammar graph
graphic grasp grass grave gravel gravity graze grease green grid grief grill
grind grip groove gross ground group grove grow growth grub grunt guard guess
guide guild gut gypsum habit hack hackathon hacker hail hair half hall
halo halt hamster hand handle hang harbour hard hardy harm harness harsh
harvest hatch hawk hay hazard head heal health heap hear heart hearth heat
heaven heavy hedge heel height helix helm help herb herd hertz
hexagon hibernate hiccup hide high hinge hint hip history hitch hive
hoard hobby hoe hoist hold hole hollow hologram home honey hood hoof
hook horizon horn horse host hostel hotel hound house hover hub huge hull hum
human humid hunger hunt husk hut hybrid hydrogen hydrant hymn hypothesis
ice icon idea ideal idle idol ignite ignore image imagine imitate immense
immerse immune implant import inbox incubate index indicate indoor induce
induct inert infant infect infer infest infinite infix inflame inflate inflect
influx inform ingenious inhale inherit inhibit initial inject inland inlet
inner input insect insert inside inspect inspire install instance instant
insulin intake integer intense interact intercept interest interface interim
interior internal internet interpret interrupt intersect interval invent
invert invest invite invoke involve iodine ion iron island isle isotope issue
item ivory jab jack jackal jacket jade jagged jam jar jaw jay jelly jerk jest
jet jetty jewel jingle job jockey joint joule journey joy joystick judge jug
juggle juice jumbo jump jungle junior junk jury just jut keen keep kennel
kept kernel kettle key keyboard kick kid kidney kill kind kindle kinetic king
kiosk kiss kit kitchen kite kitten knead knee knew knife knight knit knob
knot know knowledge knuckle koala lab label labour ladder lake lamb lamp lance
land laptop large larva laser latch late latent latitude launch lava law lawn
layer lead leaf league leak lean leap learn lease least leather leave lecture
ledge left leg legacy legal legend leisure lens less lesson letter level lever
lichen lie life lift light lighten like lilac limb lime limit limp line linear
linen liner link lion liquid list listen litre liter little live liver lizard
llama load loaf local locate lock locus locust lodge loft logic login logo
lonely look loop loose lorry lose loss lot loud lounge louse love lower lucid
lunar lunch lure lurk lush luxury lymph magnet magma mail main maize
major make malaria mall malt mammal manage mane mango manner manual manufacture
manure many map maple marble march margin marine mark market marry marvel mask
mass master match mate maths matter mature maximum maze meadow meal mean
measles measure meat medal media medic medical medium meet mega melon melt
member memo memory menace mend menu mercury merge merit mesh mess metal
meteor meter method metre metric micro microbe microscope midday middle might
migrate mild mile milk mill mimic mineral minor minus minute miracle mirage
mirror mist mistake mite mix mobile mock modem modern modify module molar mold
molecule moment momentum monarchy money monitor monkey month moon moral
mosaic mosquito moss motel motif motion motor motto mould mound mount mouse
mouth movie mud multiply murmur muscle museum music mute mutual muzzle mystery
myth nail naive naked name nano nap narrate narrow nasal nation native nausea
naval nave navy near nebula nectar need needle neglect nerve nest nettle neural
neuron neutron never new news newton nibble niche nickel niece night nimble
nimbus nine nineteen ninety nip noble node noise nominal none noodle noon
normal north nose notch note notice notion noun nourish novel novice now
nozzle numb number nurse nut nylon oak oar oasis oat obey object oblige oboe
observe obtain obtuse obvious occasion occupy occur ocean octave odd ode offer
office often oil ointment old olive omega omit once onion only ooze open opera
operate opinion oppose optician option orbit orchard order organ origin
ornament oscillate other otter ought ounce outer outline output oval oven over
overflow owl owner oxide oxygen oyster pace pack packet pact pad paddle paddy
page paid pail pain paint pair pale palm panel panic paper parade parcel pardon
parent park parrot part particle party pass past paste patch patent path patio
pattern pause pave paw pay pedal peer pelt pen pencil pendent penny people
pepper perch period perish permit persist person pest petal petrol phase phone
photo phrase pick pickle picture piece pier pierce pigment pile pill pillar
pilot pin pinch pine pink pint pioneer pipe pirate piston pitch pity pivot
pixel pizza place plague plain plan plane planet plank plant plasma plaster
plate plateau platform plead plot plough pluck plug plum plume plump plunge
plural pocket podium poem poet point poison polar pole pollen pollute ponder
pony pool poor poppy popular porch pore porous port portal pose posit position
possess possible post poster postman postpone potato potent pouch poultry pound
pour powder power practise praise prawn pray preach precede precis precise
predict prefer prefix pregnant premium prepare present preserve press pressure
price prick prime prince print prior prism prison private prize probe process
prodigy produce product profuse project prompt proof propel proper
property prophet prose prove proverb provide province prune pub public pulse
pump punch pupil puppet purchase pure purple purpose purse pursue push puzzle
python quack quail quake qualify quality quantity quart quartz queen quench
query quest queue quick quiet quilt quirk quit quite quiz quote rabbit race
rack radar radiate radio radish raft rag rage raid rail railway rain raise
rake rally range rank rapid ratio rattle raven reach react read ready realm
reap rear reason rebel recall receive recent recess recipe reckon record
recover recur red redden redeem reduce reed reef reel refer refine reflect
reform refresh refuge refund refuse regard regime region register regular
rehearse reign relay release relief rely remain remark remedy remember remote
remove render renew rent repair repeat repel reply report request rescue
research resemble reserve resist resolve resort resource respect respond rest
restore result resume retain retire retort retreat return reveal review revise
revive reward rhyme rhythm ribbon rice rich riddle ride ridge rifle right rigid
rinse ripen rise risk rival river rivet roam roar roast rob robe robin robot
robust rock rocket rod rogue role roll roman roof rook room roost root rope
rose rot rotate rotor rough round route routine row royal rubber rubbish ruby
rudder rug ruin rule ruler rural rush rust rustic sack sacred sacrifice saddle
safe sage said sail saint salad salary salmon salute sample sane sang sanitary
sapphire sari sash sat satellite satisfy saturate sauce saucer save say scale
scallop scalp scan scant scar scarce scare scarf scatter scene scent scheme
scholar school science scissors scoop scope scorch score scour scout scrap
scrape scratch scream screen screw scroll scrub sculpt seal seam search season
seat second secret sector see seed seek seem seen seldom select self sell
senate send sense sensor sentence sequel series serious serve server service
sesame session seven sever severe sew shade shadow shaft shake shall shallow
shame shape share shark sharp shatter shave she shear shed sheen sheep sheer
sheet shelf shell shelter shift shine shiny ship shirt shiver shock shoe shoot
shop shore short shout shove show shower shred shrewd shrub shut shuttle shy
sick side sieve sigh sight sign signal silent silk silly silver similar simple
since sincere sinew sing single sink sir siren sister sit site six sixth sixty
size skate skeleton sketch skill skin skip skirt sky slab slack slam slang
slant slap slate slave sleep sleet sleeve slice slide slight slim sling slip
slope slot slow slug smack small smart smell smile smoke smooth snack snail
snake snap snare snatch sneak sneer sneeze sniff snooze snore snow soak soap
soar sober soccer socket soda sofa soft software soil solar soldier
sole solid solo solve sonar sonic soot sore sort soul sound soup sour source
south space spade span spare spark sparrow speak spear special species
specific specimen speck speech speed spell spend sphere spice spider spill
spin spiral spirit spite splash spleen splendid split spoil spoke sponge
spoon sport spot spouse spray spread spring sprinkle sprite sprout spur
square squash squeak squeeze stable stack stadium staff stag stage stain
stair stake stale stalk stall stamp stand star starch stare stark start state
static station stay steady steak steal steam steel steep steer stem
stench stencil step stern stew stick sticky stiff still sting stir stitch stock
stole stomach stone stood stool stop store storm story stove straight strain
strait strange strap straw stray streak stream street strength stress stretch
strict stride strike string strip stripe strive stroke stroll strong study
stump stun style subject submit subtle subtract suburb succeed success such
suck sudden suffer suffix sugar suit sum summer summit summon sun super superb
supper supply support suppose surface surge surgeon surname surplus survey
survive suspect suspend swallow swamp swan swap swarm sway swear sweat sweep
sweet swell swift swim swing switch sword symbol syrup system table tablet
tack tackle tact tag tail take tale talent talk tall tame tan tank tap tape
taper tar target tariff task taste taught teach team teeth tell temper temple
ten tend tender tendon term terrace terrible test text thank thaw their theme
then theory there thermal these thick thin thing think third thirst thirteen
thirty thorn those though thought thousand thread threat three threw thrill
thrive throat throb throne throw thrust thumb thunder tick ticket tidal tide
tidy tiger tight till timber time tin tiny tissue title to toad toast today toe
together token told toll tomato tomb ton tone tongue tonic tonight tool tooth
top topic torch torrent tortoise total touch tough tour towel tower town trace
track tract trade traffic tragic trail train trait tramp transact transfer
transform transit translate trap trash travel tray tread treasure treat treaty
tree trek tremble trench trend trial tribe trick trickle trim trip triumph
troop trouble trough trout truant truck true trumpet trunk trust truth try tub
tuck tug tulip tumble tumor tuna tune tunnel turbine turkey turmoil turn turtle
tutor twelve twenty twice twig twin twist type typhoid tyrant tyre ulcer ultra
umber umbrella umpire unable uncle uncover under undergo underlie underneath
undo union unit unite universe unload unlock unpack until up uphill
upper upright upset urban urge urgent urine use usual utter vacant vague vain
valid valley value van vanish vapour variety vary vase vast vault veil vein
velvet vendor venom vent verb verdict verge verse versus very vessel veto vex
vibrate vice victory view vigil vigour village vine vinegar violate violin
virus visit vista vital vivid vocal voice void volcano volt volume volunteer
voyage vulgar vulture wafer wag wagon wail waist wait wake walk wall wallet
wander wane want war ward wardrobe warm warn warp warrant wash wasp waste
watch water watt wave wax way weak wealth weapon wear weather weave web wedge
week weigh weight welcome weld well west whale wharf what wheat wheel when
where whether which while whisper white whole whose why wick wide width wife
wig wild will willow win winch wind window wine wing wink winner winter wipe
wire wisdom wise wish with withdraw within without witness wizard wolf woman
women wonder wood wool word wore work world worm worry worth would wound
woven wrap wreck wrest wrestle wrist write writer wrong yard yarn year yeast
yell yellow yield yoke young youth zebra zero zigzag zinc zip zone zoo zoom
""".split()

# Tier 3b: India, proper nouns, dates, numbers, compounds, irregular forms.
_TIER_3B = """
aadhaar andhra arunachal assam autorickshaw ayurveda banana banyan bengal
bengali betel bharatanatyam bihar biryani bombay brahmaputra buddha buddhist
calcutta carnatic caste chandigarh chappal chennai chhattisgarh chowkidar
coconut coriander crore cumin curd curry darjeeling deepavali delhi desi
dhoti divali diwali dosa dulhan durga eid festival ganga ganges
ganesh gandhi ghat goa gujarat gujarati gurgaon gurudwara guru haryana
himachal hindi hindu holi hyderabad idli jammu january february march april
june july august september october november december monday tuesday wednesday
thursday friday saturday sunday january february march april june july august
onam pongal navratri dussehra holi diwali eid christmas ramadan ramzan bakrid
muharram guru nanak vaisakhi baisakhi ugadi gudi padwa puthandu vishu
pooram thrissur kochi kozhikode kollam palakkad kannur kasaragod
malappuram wayanad idukki pathanamthitta alappuzha kottayam ernakulam
thiruvananthapuram trivandrum kerala karnataka tamil nadu telangana andhra
maharashtra madhya pradesh uttar pradesh bihar bengal odisha odia assam
punjab haryana rajasthan gujarat goa kashmir ladakh sikkim manipur mizoram
tripura nagaland meghalaya arunachal delhi mumbai kolkata chennai bangalore
bengaluru hyderabad ahmedabad pune surat jaipur lucknow kanpur nagpur patna
indore bhopal vadodara varanasi agra meerut allahabad prayagraj amritsar
ludhiana jalandhar jammu srinagar shimla dehradun ranchi bhubaneswar cuttack
rourkela salem coimbatore madurai trichy tiruchirapalli nellore vijayawada
visakhapatnam vizag warangal mysore mysuru mangalore hubli belgaum kolhapur
nashik aurangabad solapur amravati thane kalyan ulhasnagar faridabad ghaziabad
noida gurugram chandigarh mohali panchkula jodhpur kota bikaner ajmer udaipur
alwar bharatpur sikar jhunjhunu bhilai durg raipur bilaspur korba ujjain
gwalior jabalpur satna katni dewas ratlam morena sagar rewa khandwa
burhanpur betul chhindwara damoh datia guna hoshangabad jhabua mandla
neemuch panna raisen rajgarh sehore seoni shahdol shajapur sheopur
shivpuri tikamgarh umaria vidisha ashoknagar anuppur alirajpur barwani
dindori harda mandsaur singrauli sidhi
zero one two three four five six seven eight nine ten eleven twelve thirteen
fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty
sixty seventy eighty ninety hundred thousand lakh crore million billion first
second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth
thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth
twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth
hundredth thousandth once twice thrice january february march april may june
july august september october november december monday tuesday wednesday
thursday friday saturday sunday weekend weekday fortnight morning afternoon
evening night midnight noon dawn dusk today tomorrow yesterday daily weekly
monthly yearly annually
""".split()

# Tier 3c: compounds, irregular verbs and nouns, contractions.
_TIER_3C = """
afternoon airmail airport alumnus alumni alumna alumnae anybody anyhow
anyone anything anyway anywhere afternoon armchair armpit aside asleep
awoke awoken
background backup backward ballroom bankrupt barefoot baseball basketball
bathroom bathtub battlefield become became been before begin began begun
behold behave behind being below bent beside between
beyond bicycle birthday biscuit blackboard blacksmith blindfold blown blue
blueprint bookstore born borrow bottom bound boundary brainstorm
breakfast bridegroom bridesmaid broadcast broken broke brought brown brought
buckwheat buffalo built bullock bungalow burst bury bustle bypass
cabbie came cannot caretaker cartoon catchup ketchup catfish cattle
caught causeway ceasefire chalkboard cheapskate checkup cheerful
cheque child children chose chosen classroom cleanse cleanup clerk climate
closeup cobweb cockroach coconut coffee coffeepot cogent
comeback commonplace compass compound understood
copycat cornflakes cornflour corridor couch could council counsel count
courthouse courtyard cowboy cowshed crackdown crayon cream
cricket cross crosscheck crossroads crown cupboard curb cut
cutoff daily dairy daytime dead deer defeat defend desktop grew
diary dishwasher divide dizzy does done door doorbell doorway dotcom doughnut
dove down download downpour dragonfly drain dried
drift drill drink drove drug drunk dry duck duct dumb duty dwarf dwell dying
earthquake ebook edgewise eight eighteen eighty elbow elder elect eleven
email embed ending endless endure enemy engine enjoy enough enter entire
entry envelope epic essay everyday everyone everything exact excel except
extra eyeball eyebrow eyesight facebook farewell father fault
feedback fell felt fence fever few fibre field fifteen fifth fifty fight
figure file fill film final fireplace fireworks first fishbone flash
flew flies flipchart floorcloth flowerbed flown focus football footpath
footprint foremost foresee foretell forget forgot forgotten forgive forgot
forgiven fork formal former fought found fourteen fourth freeze fridge friend
frost frostbite frozen fruit fulfil fulfill fund furlong further
furthermore future gadget gain gearbox gmail grew grown growth guardian guide
guilty gunfire habit haircut hallmark hamster handbook handkerchief handful
handshake handsome hangout hardware headline headmaster health
healthcare heard heart heater heaven held herself highway hill
himself hippo hired hit homework honeymoon hoodwink horse
horsepower hostel hotel household however human humble hunger hunter hurry
husband hush ice ice cream icecream inbox income indoors input inside insight
install instant instead insure intact into invite invoke iron issue itself
jackfruit jaggery jam jar jawan jelly jewel job jockey jolt journal journey
joy judge juggling juice jump jungle junior jury justice justify keeping
kept keyboard kick kickoff kid kindle king kitchen kite kitten knew knock
knockout know knowledge known koel ladder lady laid lain laptop laser latch
lay ledge leech left leftover leg lend lent lens lentil lesson letter lettuce
level library licence license light lightning like lily limelight lineup link
lipstick list listen little live load loaf loan lobby local locate lock locomotive
logbook login logout lookout lord luggage lunch lying machine made
magnet maid maiden mail mailbox main makeup malaria male mall mane mango man
mankind manpower manual marble march margin marigold mark marketplace marry
marvel mask master match mate mathematics maths matter maybe mayor maze meadow
meal mean meant medal media meet melody melon melt member memo memory menace
mend menu merge merit merry met metal method metro mice midnight midst might
mild mile milk mill mimic mind mine mischief miss mission mistake mister mix
mobile mock model modem modern module molar mold moment money monitor monkey
month mood moon morning mosquito motel mother motor motorcycle mount mouse
mouth movie mr mrs ms much muesli mug multiply murmur muscle museum
music must myself nail naive name nap nephew nerve nest netball network never
new news newspaper next night nightfall nightingale nine nineteen ninety nobody
noble noise none noon normal north nose note notebook nothing notice
noun novel nowhere number nurse nut oak off office often oil old olive
once onion online only open opera operate opinion oppose option orange orbit
order organ other ought ounce outdoor outer outline output outside over overcast
overcoat overcome oversee overtime owe own owner oxford oxygen oyster paddy
page paid pail pain paint pair pane panel panic paper paperback parade parcel
pardon parent park part partly pass passport past pasta patch patent path patio
pay pea peace peanut pear peasant pen pencil penny people pepper perform period
permit person phone photo phrase piano pick pickle picnic picture piece pin
pine pink pitch pity pizza place plain plan plane planet plant plate
plateau platform play playback playground plead please plight plot plough plug
plum plus pocket poem poet point poison polar pole polite pond pony pool poor
popcorn poppy post postbox poster postman postpone potato pound pour powerpoint
practise prank prawn pray preach preschool present press price pride print
prize probe profit programme propel prose prove proverb provide pub public pull
pulse pump punch puncture pupil puppy pure purple purse push puzzle python
quake queen query queue quick quiet quilt quit quite quiz rabbit race radio
railway rain rainbow raise range rank rash rat rate rather reach react read
ready realm reap rear rearm reason recall receive recent recipe reckon record
redo reduce refer refresh regard relay release relief rely remain remark remedy
remember remind remit remote remove renew rent repair repay repeat repel reply
report rerun rescue research reserve reset resist resolve resort rest restroom
retake retire return retype reunion reveal review revise revive rhyme ribbon
rice rich ride ridge right ring risen river road roar roast robot rock role roll
roof room root rose rotten rough round route routine row royal rubber rugby
rude rug ruin rule run rural rush sack safe said sail saint sale salon salt
same samosa sand sandal sat satellite sauce save say scarf scene school science
score screen screw search season seat second secret section see seed seek seen
self selfie sent series serve set setup seven shade shadow shake shall shame
shape share sharp shave sheep sheet shelf shell shift shine ship shirt shoe
shone shook shoot shop short shout shown shut shy sick sightseeing sign signal
silent silk silver simple since sing singer single sink sir sister sit site
six sixty size skate sketch skill skin skull sleep slept slice slid slide slight
slim slip slope slot slow small smart smell smile smoke snake snow so soap
soccer society sock soda sofa soft software soil solar soldier sole solid solve
son song soon sore sorry sort sought sound soup south space spare spark speak
special speech speed spell spend spice spill spoke spoken spoon sport spot
spread spring square stable staff stage stain stair stand star stare start state
station stay steady steak steal steam steel steep steer stem step stick still
sting stood stool stop store storm story stove straight strange stream street
stretch strict strike string stripe strive stroke stroll strong stuck student
study subject sublet submit succeed such sudden suffer suffix sugar suit sum
summer sun sunlight sunrise sunset sunshine superb supper supply support
suppose sure surface survive suspect swallow swam swim swing switch sword sworn
table tablet tack tail tailor take taken tale talk tall tank tap tape task taste
taught teach team tear teeth tell ten text thank that their theme then there
these thick thief thin thing think third thirteen thirty those though thought
thousand three threw throat through thrown throw thumb thunder tick ticket tide
tidy tie tiger tight till time tiny tired title toast today toe together told
tomorrow tongue tonight took tool tooth top topic total touch tough tour tower
town track trade traffic trail train transfer translate travel tray tread treat
tree trek trend trial tribe trick trip truck true trunk trust truth try tshirt
tulip tumble tuna tune tunnel turkey turn turtle tutor twelve twenty twice
twig twin twist type undergo understand understood underwear undo undone
unfair unfold union unit unite unknown unlock unpack until up upload uphold
upper upset urban urge use usual utter vacant vague valid value van vanish
variety vary vast veil vendor venue verb verse very video view village vineyard
vinegar violin virus visa visit vital vivid voice vote voyage wage wait wake
walk wall wallet want war warm warn wash waste watch water wave way weak wear
weather weave web wedding week weigh weight welcome well went were west wet
what wheat wheel when where whether which while white whole whose why wide
wife wild will win wind window wine wing winner wipe wire wisdom wise wish
with within without witness woke woken wolf woman women wonder wool word wore
work world worn worry worth would wound woven wrap wreck write writer writhe
wrong wrote yacht yard year yell yellow yield young youth zebra zero zip zoom
ain't aren't can't couldn't didn't doesn't don't hadn't hasn't haven't isn't
it's let's shan't she's shouldn't that's there's wasn't weren't won't wouldn't
could've should've would've i've you've we've they've i'd you'd he'd she'd
we'd they'd i'll you'll he'll she'll we'll they'll i'm you're we're they're
o'clock ma'am y'all
""".split()

# Tier 3d: stragglers - confusable pairs, rule gaps, compounds, India words.
_TIER_3D = """
flue fluent diarrhoea diarrhea pyjama pyjamas pajamas stationery stationary
envelop prophesy compliment illicit eminent immanent serial patience currant
dual foreword navel peddle rein raze ray rote troupe valence valance vial
vise whey weed whet whit wrack reek wreak wring yore canvass grisly grizzly
hangar heroin jester lyre marshal spacious steppe tier thyme tow vane wile
teem creak sere serge cession lightening frightening misunderstood napkin
tablecloth bedsheet pillowcase shampoo toothbrush toothpaste bucket utensil
doormat garbage cabbage atta maida rava suji poha upma vada sambar rasam
kheer rabri kulfi falooda chai kaapi pakora pakoda bhaji pani golgappa
phuchka chaat tikki kebab kabob tandoor tandoori pulao pilaf khichdi
tamarind kokum buttermilk lassi chaas sherbet sorbet nimbu shikanji achar
papad papadam poppadom appam puttu idiyappam pathiri kappa tapioca chembu
chaya kattan payasam sadya onasadya pookkalam pookalam vallamkali kathakali
chenda melam thiruvonam thiruvathira perunnal ambalam palli pallikoodam
madrasa madrassa vidyalaya pathshala anganwadi balwadi panchayat sarpanch
councillor councilor counsellor counselor municipality operation cooperation
corporation collector visitor sailor traitor creator donor mentor juror
sculptor inventor investor auditor editor director inspector contractor
conductor competitor supervisor supervise advisor adviser senator dictator
narrator translator curator janitor pastor realtor surveyor purveyor conveyor
doorstep footstep doorman milkman fisherman policeman businessman chairman
spokesman spokeswoman statesman fireman handyman nobleman cameraman postmen
milkmen fishermen policemen businessmen chairmen spokesmen spokeswomen
firemen doormen handymen noblemen statesmen cameramen gentlemen gentlewoman
gentlewomen oxen mice lice geese physics zoology geology astronomy astrology
gastronomy economy economics civics geography statistics accountancy
entrepreneur accomplish establish marriage orphanage vintage percentage
mileage wastage hosteller hostelite supplementary compartment backlog arrear
revaluation photocopy photostat xerox stencil fevicol roughbook fairbook
scrapbook slambook lunchbox tiffin backpack rucksack duffel duffle raincoat
windcheater cardigan pullover mitten beanie sweatshirt hoodie trenchcoat
kurta salwar kameez churidar dupatta leggings jeggings palazzo lungi mundu
veshti sherwani nehru tagore kalam bose bhagat singh kaur sharma verma gupta
agarwal agrawal arun meera anita sunil deepa kavya navya divya diya arjun
rohan mohan sohan sneha pooja neha aman vikas aditya ishan ishaan krishna
radha sita gita geeta ramayana mahabharata bhagavad veda upanishad purana
roti naan kulcha bhatura thepla dhokla jalebi laddu ladoo rasgulla rasogolla
gulab jamun barfi burfi halwa halva veena sitar tabla tanpura tambura
harmonium kolam rangoli aarti bhajan kirtan qawwali iftar sehri zakat roza
puri paratha parotta porotta chapati chappati ketchup tote carrybag paperbag
darling sibling homesick seasick carsick airsick handbag washroom cloakroom
staffroom storeroom godown strongroom everywhere somewhere anytime meanwhile
nowadays throughout ourselves yourselves acknowledge upward downward outward
onward homeward northward southward eastward westward madden maid ration
certificate marksheet hallticket admitcard classmate benchmate deskmate
roommate teammate playmate schoolmate soulmate checkmate prefect assembly
attendance register classwork schoolwork coursework fieldwork teamwork
information baggage everywhere somewhere anytime meanwhile nowadays throughout ourselves
yourselves acknowledge upward downward outward onward homeward northward
southward eastward westward madden maid ration certificate marksheet
hallticket admitcard classmate benchmate deskmate roommate teammate
playmate schoolmate soulmate checkmate prefect assembly attendance
register classwork schoolwork coursework fieldwork teamwork information
baggage elsewhere upstairs downstairs headmistress warden storey attic
cellar terrace balcony verandah veranda portico foyer lobby corridor
gallery staircase elevator escalator ramp railing banister bannister
grill gate compound hedge ditch well borewell tubewell handpump sump
tank overhead shelf rack almirah cupboard drawer chest trunk suitcase
briefcase flask thermos jug jar mug glass tumbler plate saucer bowl
basin vessel ladle spoon fork knife spatula rolling chakla belan tawa
kadhai cooker frypan saucepan kettle toaster mixer grinder fridge
freezer oven stove burner lighter matchbox candle lamp bulb fan heater
geyser iron washing clothesline broom mop wiper duster dustpan hammer
nail screw screwdriver pliers wrench spanner drill saw axe hatchet
shovel spade rake hoe sickle scythe pitchfork wheelbarrow ladder rope
string twine thread needle thimble button zipper hook snap fastener
safety hairpin rubber paperclip staple stapler punch file folder binder
bulldog paperweight bookmark highlighter marker crayon pastel charcoal
canvas easel apron smock bib coaster doily runner centrepiece vase
flowerpot planter pot soil manure compost fertiliser fertilizer pesticide
insecticide fungicide herbicide weedkiller carpenter mason plumber
electrician welder painter mechanic driver cleaner sweeper watchman
gardener cook chef bearer servant helper assistant peon clerk typist
stenographer receptionist cashier accountant manager officer boss chief
head master mistress teacher professor lecturer tutor principal dean
chairman chairperson secretary treasurer member volunteer worker
labourer coolie porter loader pilot captain soldier policeman constable
inspector superintendent commissioner magistrate judge lawyer advocate
attorney prosecutor defendant witness plaintiff jury verdict judgment
judgement sentence bail parole probation fine penalty punishment reward
award prize medal trophy shield citation honour jail prison lockup cell
custody remand trial hearing appeal petition case lawsuit dispute claim
complaint challan summons warrant notice raid search seizure arrest
release acquittal conviction discharge dismissal suspension transfer
posting promotion demotion retirement pension gratuity bonus increment
allowance house conveyance casual earned maternity study sabbatical
holiday vacation weekend overtime shift duty roster late early permission
outing uniform diary almanac calendar timetable schedule routine period
interval recess chalk duster projector screen pointer globe map atlas
chart model specimen sample kit goggles gloves litmus chemical reagent
acid alkali base salt solution mixture compound element atom molecule
proton neutron electron nucleus orbit shell valency formula equation
reaction product reactant catalyst heat light sound magnet electricity
current voltage resistance power circuit wire switch plug socket fuse
battery generator motor heater bulb diode transistor chip processor
laptop tablet smartphone charger cable keyboard mouse monitor printer
scanner speaker headphone earphone webcam lens tripod drone robot toy
puzzle block doll teddy balloon kite yoyo marbles hopscotch skipping
cricket football hockey kabaddi kho volleyball basketball badminton
tennis squash racquet bat stump glove pad helmet jersey boot whistle
referee umpire coach match tournament league cup final semifinal
quarterfinal score goal run wicket over bye wide sixer four boundary
century duck innings declaration toss coin pitch ground stadium pavilion
gallery stand floodlight scorer scoreboard announcer crowd cheerleader
flag banner poster placard slogan chant song anthem march drill yoga
meditation prayer pledge oath promise vow discipline punctuality
honesty truth nonviolence tolerance respect elder value moral fable
parable legend myth epic ballad poem poetry rhyme rhythm verse stanza
couplet sonnet ode elegy satire tragedy comedy drama play skit mime
dance tune melody harmony beat tempo pitch scale raga tala instrument
drum dholak ghatam kanjira morsing flute nadaswaram shehnai saxophone
trumpet trombone clarinet oboe bassoon harmonica accordion casio guitar
harp banjo mandolin ukulele drums cymbals triangle tambourine maracas
bongo xylophone gong bell chime whistle horn bugle conch shankh damru
dhol tasha djembe thavil udukai parai pulikali kummi kolattam dandiya
garba bhangra giddha lavani tamasha nautanki jatara bhavai puppet
street nukkad monoact mimicry costume makeup mask prop stage curtain
backdrop light sound wings audience applause encore review critic
newspaper magazine journal editorial article column feature headline
byline dateline caption photo cartoon comic crossword sudoku horoscope
weather sports business cinema entertainment lifestyle health education
job classified matrimonial obituary announcement tender auction sale
discount offer festival exchange cashback coupon voucher gift loyalty
order delivery shipping courier post parcel packet envelope stamp seal
letterhead visiting invitation greeting shower wedding birthday
anniversary sweet dry fruit chocolate mithai faral chakli murukku
thattai ribbon mixture namkeen bhujia pickle thokku chutney podi
powder garam masala chilli turmeric coriander cumin jeera mustard rai
fenugreek methi fennel saunf cardamom elaichi clove cinnamon dalchini
anise mace nutmeg saffron asafoetida hing pepper pippali ginger sukku
poppy sesame til gingelly coconut groundnut sunflower bran vanaspati
dalda ghee butter cream malai paneer chenna khoa mawa curd yogurt milk
toned skimmed condensed dairy booth parlour kirana supermarket
hypermarket mall bazaar market mandi sabzi flea weekly shandy mela
exhibition expo trade annual founders republic mothers fathers
friendship pongal vishu dussehra navratri durga ganesh janmashtami
shivratri karthigai thaipusam panguni uthiram ugadi padwa
baisakhi vaisakhi bihu bohag rongali poila shital sarhul karma navakhai
nuakhai raja parba chhath teej karva rakhi bandhan govardhan
satyanarayan kumbh magh shravan sawan aadi thai maasi purattasi aippasi
karthigai margazhi mattu kaanum bhogi lantern kandeel akash diya pharal
karanji shankarpali besan motichoor boondi jangri imarti katli rasmalai
chamcham sandesh payesh phirni sevaiyan khurma meetha tehri bisibelebath
sarkarai pulihora daddojanam gongura pachadi avakaya majjiga tumbler
dabara davara kumbakonam madras kachori dabeli misal usal tawa khari
osmania rusk nankhatai maska ladi kadak brun irani samovar kehwah kahwa
sulaimani suleimani chukku panangkarkandu karupatti marayoor kanthari
mulaku kariveppilai karapincha murungai vendakkai bhindi okra brinjal
kathirikai baingan karela pavakkai padaval poosanikai parangikai pumpkin
sorakkai peerkangai turai parwal tindora kovakkai kothavarangai avarakkai
pattani chickpea kabuli kala moong pachai urad ulundu tuvaram masoor
kadalai siruparuppu ulutham kollu matki rajma lobia karamani cowpea
soyabean verkadalai peanut nilakadalai cashew mundiri almond badam pista
pistachio walnut akhrot raisin kishmish khajur fig anjeer apricot khubani
prune peach perikai santra mosambi elumichai thiratchai mathulai pappali
koyya palapazham vazhapazham nendran robusta poovan rasthali annasi
muskmelon cantaloupe seethapazham soursop mulluseetha vilampazham naval
jambakka jambu carambola kiwi avocado sapota chikoo chickoo litchi lychee
rambutan mangosteen durian breadfruit seema elaneer karikku nungu toddy
kallu neera padaneer karumbu vellam bella gul shakkar khandsari thene
treacle molasses agave toor chana gram aloo anda panda santa fanta coke
pepsi mirinda thumsup maaza frooti appy fizz ball elephant octopus
jellyfish starfish seahorse lobster squid penguin rhino rhinoceros
hippopotamus kangaroo reindeer toward towards dragon castor worse worsen
gladden tighten loosen fasten hasten moisten christen glisten harken
roughen toughen coarsen hoarsen sulphur sulfur phosphorus potassium
sodium calcium magnesium aluminium aluminum cobalt platinum titanium
chromium tungsten radium radius uranium radon neon argon krypton xenon
helium nitrogen fluorine chlorine bromine
""".split()

# Tier 3e: fallout words - valid words the checks proved must be known.
_TIER_3E = """
plenty skilful wilful instill enroll instal instalment enthrall courageous
dangerous nervous anxious mysterious victorious glorious tedious zealous
rebellious marvellous marvelous scandalous miraculous ridiculous meticulous
vivacious tenacious audacious fallacious written accommodation friendship
relationship fellowship scholarship internship citizenship membership
ownership craftsmanship penmanship get tore swore sold ran disgrace
disgraceful environment given torn hidden shaken beaten eaten bitten
smitten gluten ridden driven riven stricken humor armor armour rigour
rigor vapor savor savour tumour splendor ardor ardour clamor apologise
apologize summarise summarize customise customize plastic nature crab
grey tire kerb odor theatre theater yourself abroad learnt everybody
suggest suggestion digestion congestion ingestion exhaustion
""".split()






_VOWELS = frozenset("aeiou")


def _is_cvc(word):
    """Short-vowel ending that doubles its final consonant (run, stop)."""
    return (3 <= len(word) <= 8 and word[-1] not in _VOWELS | {"w", "x", "y"}
            and word[-2] in _VOWELS and word[-3] not in _VOWELS)


def _consonant_y(word):
    return len(word) >= 4 and word.endswith("y") and word[-2] not in _VOWELS


def _expansions(word):
    """Regular inflections as (form, targets) pairs.

    targets=True forms can be suggested as corrections; the rest only
    count as known spellings (they include overgenerated forms such as
    "stoped", which must never be suggested but also never flagged).
    """
    out = []
    t = out.append
    t((word + "s", True))
    if word.endswith(("s", "x", "z", "ch", "sh")) or (
            word.endswith("o") and not word.endswith("oo")):
        t((word + "es", True))
    cy = _consonant_y(word)
    if cy:
        t((word[:-1] + "ies", True))
        t((word[:-1] + "ied", True))
        t((word[:-1] + "ily", True))
        t((word[:-1] + "iness", True))
        t((word[:-1] + "iful", True))
        t((word[:-1] + "iable", True))
        t((word[:-1] + "ier", True))
        t((word[:-1] + "iest", True))
    cvc = _is_cvc(word)
    if word.endswith("e"):
        t((word + "d", True))
        t((word[:-1] + "ing", True))
        t((word[:-1] + "er", True))
        t((word[:-1] + "est", True))
        t((word[:-1] + "ly", False))
        t((word[:-1] + "ful", False))
        t((word[:-1] + "less", True))
        t((word[:-1] + "y", True))
        t((word[:-1] + "able", False))
        t((word[:-1] + "ion", True))
        t((word[:-1] + "ment", True))
        if word.endswith("dge"):
            t((word + "ment", True))
        else:
            t((word + "ment", False))
        if word.endswith(("ce", "ge")):
            t((word + "able", False))
    else:
        if not cy:
            t((word + "ed", not cvc))
            t((word + "er", not cvc))
            t((word + "est", not cvc))
        t((word + "ing", not cvc))
        if word.endswith("ie"):
            t((word[:-2] + "ying", True))
        elif word.endswith(("ee", "ye", "oe")):
            t((word + "ing", True))
    if not cy:
        t((word + "ly", False))
        t((word + "ful", False))
        t((word + "ness", True))
        t((word + "able", False))
    t((word + "less", True))
    t((word + "y", False))
    t((word + "en", False))
    if not word.endswith("e"):
        t((word + "ment", True))
    if cvc:
        doubled = word + word[-1]
        t((doubled + "ed", True))
        t((doubled + "ing", True))
        t((doubled + "er", True))
        t((doubled + "est", True))
        t((doubled + "y", True))
        t((doubled + "en", True))
    for prefix in ("un", "re", "dis"):
        t((prefix + word, False))
    return out


def _deletes(word, max_distance=2):
    """All strings formed by deleting up to max_distance characters."""
    found = {word}
    queue = [word]
    for _ in range(max_distance):
        nxt = []
        for current in queue:
            for i in range(len(current)):
                cut = current[:i] + current[i + 1:]
                if cut not in found:
                    found.add(cut)
                    nxt.append(cut)
        queue = nxt
    found.discard(word)
    return found


def _build_index():
    known = set()
    targets = {}
    for tier, words in enumerate(
            (_TIER_0, _TIER_1, _TIER_2, _TIER_3A, _TIER_3B, _TIER_3C,
             _TIER_3D, _TIER_3E)):
        for raw in words:
            base = raw.lower()
            if base not in targets or targets[base] > tier:
                targets[base] = tier
            known.add(base)
            for form, suggest in _expansions(base):
                known.add(form)
                if suggest:
                    rank = tier + 2
                    if form not in targets or targets[form] > rank:
                        targets[form] = rank
    # Second pass: plurals of generated agent nouns (teachers, writers).
    # Known spellings only; singulars stay the suggested forms.
    for form, rank in list(targets.items()):
        if form.endswith(("er", "ies", "ful", "ness", "able", "ly", "ed",
                          "ing", "en", "ment")) and len(form) >= 6:
            known.add(form + "s")
            if form.endswith(("s", "x", "z", "ch", "sh")):
                known.add(form + "es")
    deletes = {}
    for form, rank in targets.items():
        for cut in _deletes(form, 1):
            deletes.setdefault(cut, []).append((form, rank))
    return known, deletes


_KNOWN, _DELETES = _build_index()


def _osa(a, b):
    """Optimal string alignment distance, capped above 2."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return 3
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        row_min = i
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            best = prev[j - 1] + cost
            ins = cur[j - 1] + 1
            if ins < best:
                best = ins
            dele = prev[j] + 1
            if dele < best:
                best = dele
            if (i > 1 and j > 1 and ca == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                trans = (prev2[j - 2] if prev2 is not None else 0) + 1
                if trans < best:
                    best = trans
            cur[j] = best
            if best < row_min:
                row_min = best
        if row_min > 2:
            return 3
        prev2, prev = prev, cur
    return prev[lb] if prev[lb] <= 2 else 3


def correction(token):
    """The corrected spelling of token, or None when fine or unsure.

    Only all-lowercase tokens are checked: capitalised words are left
    alone so names (Arun, Onam) are never "corrected". Distance 1
    fixes always apply; distance 2 only for words of 6+ letters.
    """
    if not token or not token.islower():
        return None
    if token in _KNOWN:
        return None
    core = token
    suffix = ""
    if core.endswith("'s"):
        core, suffix = core[:-2], "'s"
    elif core.endswith("s'"):
        core, suffix = core[:-1], "'"
    elif core.endswith("'"):
        core, suffix = core[:-1], "'"
    if len(core) < 4 or not core.isalpha():
        return None
    if core in _KNOWN:
        return None
    best = None
    seen = set()
    for cut in [core, *_deletes(core)]:
        for form, rank in _DELETES.get(cut, ()):
            if form == core or form in seen:
                continue
            seen.add(form)
            dist = _osa(core, form)
            if dist > 2:
                continue
            key = (dist, rank, form)
            if best is None or key < best:
                best = key
    if best is None:
        return None
    dist, _, form = best
    if dist == 2 and len(core) < 6:
        return None
    return form + suffix


def known_count():
    """How many spellings count as correct (for tests and logs)."""
    return len(_KNOWN)

