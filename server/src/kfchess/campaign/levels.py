"""Campaign level definitions.
"""

from kfchess.game.board import BoardType

from .models import CampaignLevel

# Belt names
BELT_NAMES = [
    None,  # 0 (unused)
    "White",  # 1: levels 0-7
    "Yellow",  # 2: levels 8-15
    "Green",  # 3: levels 16-23
    "Purple",  # 4: levels 24-31
    "Orange",  # 5: levels 32-39
    "Blue",  # 6: levels 40-47
    "Brown",  # 7: levels 48-55
    "Red",  # 8: levels 56-63
    "Black",  # 9: levels 64-71
]

MAX_BELT = 9  # Currently implemented belts


LEVELS: list[CampaignLevel] = [
    # ========== Belt 1: White (2P Standard) ==========
    CampaignLevel(
        level_id=0,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
P1P1P1P1P1P1P1P1
R1N1B1Q1K1B1N1R1
""",
        title="Welcome to Kung Fu Chess",
        description="It's like chess, but there are no turns. Win by capturing the enemy king!",
    ),
    CampaignLevel(
        level_id=1,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
R10000Q1K10000R1
""",
        title="The Elite Guard",
        description="Use your queen and rooks to trap the enemy king. Remember, pieces can move at the same time!",
    ),
    CampaignLevel(
        level_id=2,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
P1P1P10000P1P1P1
00000000K1000000
""",
        title="March of the Pawns",
        description="Advance pawns to the end of the board to promote them.",
    ),
    CampaignLevel(
        level_id=3,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000R1K1R10000
""",
        title="Flanking Strike",
        description="Attack the enemy king from both sides with your rooks.",
    ),
    CampaignLevel(
        level_id=4,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000Q1K1000000
""",
        title="Royal Couple",
        description="A king must always protect his queen!",
    ),
    CampaignLevel(
        level_id=5,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000P1P1000000
00000000K1000000
""",
        title="Step by Step",
        description="Maintain a tight formation to avoid the enemy breaking through.",
    ),
    CampaignLevel(
        level_id=6,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000B100K1B10000
""",
        title="Criss Cross",
        description="Bishops are great for closing off angles, but keep in mind that they only cover one color each.",
    ),
    CampaignLevel(
        level_id=7,
        belt=1,
        speed="standard",
        board_str="""
00000000K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00N1N100K1N1N100
""",
        title="The Four Horsemen",
        description="Knights capture only at the end of their path. Ride to victory!",
    ),
    # ========== Belt 2: Yellow (2P Standard) ==========
    CampaignLevel(
        level_id=8,
        belt=2,
        speed="standard",
        board_str="""
0000000000000000
000000P2K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000B100K1B10000
""",
        title="Bishop Blockade",
        description="Don't let the pawn advance to the end of the board!",
    ),
    CampaignLevel(
        level_id=9,
        belt=2,
        speed="standard",
        board_str="""
00000000K2000000
000000P2P2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000Q1K1000000
""",
        title="Double Trouble",
        description="Choose your angle of attack wisely.",
    ),
    CampaignLevel(
        level_id=10,
        belt=2,
        speed="standard",
        board_str="""
00000000K2000000
0000P2P2P2P20000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000P100000000
00N10000K10000R1
""",
        title="Ragtag Crew",
        description="Use the various tools at your disposal to deconstruct the enemy line.",
    ),
    CampaignLevel(
        level_id=11,
        belt=2,
        speed="standard",
        board_str="""
0000P200K2P20000
00P2P2P2P2P2P200
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000P1P1000000
R1000000K10000R1
""",
        title="Clean Sweep",
        description="Rooks specialize in sweeping up the backline.",
    ),
    CampaignLevel(
        level_id=12,
        belt=2,
        speed="standard",
        board_str="""
00P2P200K2P2P200
00P2P2P2P2P2P200
000000P2P2000000
0000000000000000
0000000000000000
0000000000000000
0000P1P1P1P10000
000000Q1K1000000
""",
        title="Queen of Blades",
        description="She rules the board and captures pawns like it's no big deal.",
    ),
    CampaignLevel(
        level_id=13,
        belt=2,
        speed="standard",
        board_str="""
P2P2P200K2P2P2P2
P2P2P2P2P2P2P2P2
0000P2P2P2P20000
0000000000000000
0000000000000000
0000000000000000
00P1P1P1P1P1P100
00N1B100K1B1N100
""",
        title="Helm's Deep",
        description="Haldir's Elves and the Riders of Rohan fight alongside Theoden.",
    ),
    CampaignLevel(
        level_id=14,
        belt=2,
        speed="standard",
        board_str="""
P2P2P200K2P2P2P2
P2P2P2P2P2P2P2P2
00P2P2P2P2P2P200
0000P2P2P2P20000
0000000000000000
0000000000000000
P1P1P1P1P1P1P1P1
00N100Q1K1B100R1
""",
        title="Attack of the Clones",
        description="May the force be with you.",
    ),
    CampaignLevel(
        level_id=15,
        belt=2,
        speed="standard",
        board_str="""
P2P2P200K2P2P2P2
P2P2P2P2P2P2P2P2
P2P2P2P2P2P2P2P2
P2P2P2P2P2P2P2P2
0000000000000000
0000000000000000
P1P1P1P1P1P1P1P1
R1N1B1Q1K1B1N1R1
""",
        title="For the Alliance!",
        description="You must put an end to the Horde once and for all.",
    ),
    # ========== Belt 3: Green (2P Lightning) ==========
    CampaignLevel(
        level_id=16,
        belt=3,
        speed="lightning",
        board_str="""
000000Q2K2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
000000Q1K1000000
""",
        title="Fast as Lightning",
        description="Lightning speed is five times faster. You can still dodge if you're quick, though!",
    ),
    CampaignLevel(
        level_id=17,
        belt=3,
        speed="lightning",
        board_str="""
0000B200K2B20000
000000P2P2000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00N100Q1K100N100
""",
        title="Lightning McQueen",
        description="McQueen and the crew race to the finish.",
    ),
    CampaignLevel(
        level_id=18,
        belt=3,
        speed="lightning",
        board_str="""
K200N20000000000
00N1000000000000
K100P10000000000
0000000000000000
0000000000000000
0000P20000P20000
0000000000000000
0000000000000000
""",
        title="Quick Attack",
        description="The enemy king is cornered. Finish him off before the reinforcements arrive!",
    ),
    CampaignLevel(
        level_id=19,
        belt=3,
        speed="lightning",
        board_str="""
00000000K2000000
0000000000000000
0000P2000000P200
00P200P200P200P2
P2000000P2000000
0000000000000000
0000000000000000
R1000000K10000R1
""",
        title="The Great Escape",
        description="Get out and grab victory before the wall closes in.",
    ),
    CampaignLevel(
        level_id=20,
        belt=3,
        speed="lightning",
        board_str="""
00000000K2B2N2R2
00000000P2P2P2P2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
P1P1P1P1P1000000
R1N1B1Q1K1000000
""",
        title="Half and Half",
        description="An empty half leaves the king vulnerable to attack.",
    ),
    CampaignLevel(
        level_id=21,
        belt=3,
        speed="lightning",
        board_str="""
000000P2P2K20000
000000P2P2000000
000000P2P2000000
000000P2P2000000
0000000000000000
0000000000000000
0000P10000000000
R1000000K1B10000
""",
        title="Pillar of Autumn",
        description="Slice through the pillar before it falls. Leave no pawn standing!",
    ),
    CampaignLevel(
        level_id=22,
        belt=3,
        speed="lightning",
        board_str="""
00000000K2000000
0000B20000000000
R200000000000000
0000000000000000
000000N200000000
00000000000000N1
00000000P1000000
00R10000K1B10000
""",
        title="Pressure Point",
        description="Survive the pressure and take control of the situation.",
    ),
    CampaignLevel(
        level_id=23,
        belt=3,
        speed="lightning",
        board_str="""
00N200Q2K20000R2
P200P20000P2P200
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00P1P1P100P100P1
R1000000K1B1N100
""",
        title="Need for Speed",
        description="Discover your inner speed demon to overcome the odds.",
    ),
    # ========== Belt 4: Purple (2P Standard) ==========
    CampaignLevel(
        level_id=24,
        belt=4,
        speed="standard",
        board_str="""
P2P2P2P2K2P2P2P2
P2P2P2P2P2P2P2P2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00P1P1P1P1P1P100
P1P1P1P1K1P1P1P1
""",
        title="Pawn Shop",
        description="You won't be able to buy your way to victory here.",
    ),
    CampaignLevel(
        level_id=25,
        belt=4,
        speed="standard",
        board_str="""
N2N2N2N2K2N2N2N2
N2N2N2N2N2N2N2N2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00N1N1N1N1N1N100
N1N1N1N1K1N1N1N1
""",
        title="A Knightly Battle",
        description="Stop horsing around!",
    ),
    CampaignLevel(
        level_id=26,
        belt=4,
        speed="standard",
        board_str="""
B2B2B2B2K2B2B2B2
B2B2B2B2B2B2B2B2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00B1B1B1B1B1B100
B1B1B1B1K1B1B1B1
""",
        title="Canterbury vs York",
        description="The bishops have succumbed to a civil war.",
    ),
    CampaignLevel(
        level_id=27,
        belt=4,
        speed="standard",
        board_str="""
R2R2R2R2K2R2R2R2
R2R2R2R2R2R2R2R2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00R1R1R1R1R1R100
R1R1R1R1K1R1R1R1
""",
        title="Captain Rook",
        description="Charge forward and break through the enemy fortress.",
    ),
    CampaignLevel(
        level_id=28,
        belt=4,
        speed="standard",
        board_str="""
Q2Q2Q2Q2K2Q2Q2Q2
Q2Q2Q2Q2Q2Q2Q2Q2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00Q1Q1Q1Q1Q1Q100
Q1Q1Q1Q1K1Q1Q1Q1
""",
        title="Queensland",
        description="The land of the Queen and the home of the King.",
    ),
    CampaignLevel(
        level_id=29,
        belt=4,
        speed="standard",
        board_str="""
R2R2R2R2K2R2R2R2
B2B2P2P2P2P2B2B2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
N1N1P1P1P1P1N1N1
B1B1B1B1K1B1B1B1
""",
        title="Fountain of Dreams",
        description="Will you find what you seek?",
    ),
    CampaignLevel(
        level_id=30,
        belt=4,
        speed="standard",
        board_str="""
P2R2Q2Q2K2Q2R2P2
00P2B2R2R2B2P200
0000P2B2B2P20000
000000P2P2000000
0000000000000000
0000000000000000
R1R1P1P1P1P1R1R1
N1N1Q1Q1K1Q1N1N1
""",
        title="Battlefield",
        description="The enemy formation is strong, but breakable.",
    ),
    CampaignLevel(
        level_id=31,
        belt=4,
        speed="standard",
        board_str="""
Q2Q2Q2Q2K2Q2Q2Q2
00N2N2N2B2B2B200
0000P2P2P2P20000
0000000000000000
0000000000000000
0000000000000000
N1N1N1N1N1N1N1N1
R1R1B1B1K1B1R1R1
""",
        title="Final Destination",
        description="No items, Fox only, Final Destination.",
    ),
    # ========== Belt 5: Orange (4P Standard) ==========
    CampaignLevel(
        level_id=32,
        belt=5,
        speed="standard",
        board_str="""
0000000000K4000000000000
000000000000000000000000
000000000000000000000000
000000000000000000000000
0000000000000000000000R1
0000000000000000000000K1
K300000000000000000000Q1
000000000000000000000000
000000000000000000000000
000000000000000000000000
000000000000000000000000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Welcome to the Arena",
        description="Four kings enter, one leaves. Use your queen and rook to hunt them down!",
    ),
    CampaignLevel(
        level_id=33,
        belt=5,
        speed="standard",
        board_str="""
0000000000K4Q40000000000
000000000000000000000000
0000000000000000000000R1
000000000000000000000000
0000000000000000000000B1
Q300000000000000000000K1
K30000000000000000000000
0000000000000000000000B1
000000000000000000000000
0000000000000000000000R1
000000000000000000000000
0000000000Q2K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Divide and Conquer",
        description="The key to victory is focusing on one thing at a time.",
    ),
    CampaignLevel(
        level_id=34,
        belt=5,
        speed="standard",
        board_str="""
0000000000K4000000000000
0000P4P4P4P4P4P4P4P40000
00P300000000000000000000
00P300000000000000000000
00P3000000000000000000B1
00P3000000000000000000K1
K3P3000000000000000000Q1
00P3000000000000000000B1
00P300000000000000000000
00P300000000000000000000
0000P2P2P2P2P2P2P2P20000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Trash Compactor",
        description="The walls are closing in!",
    ),
    CampaignLevel(
        level_id=35,
        belt=5,
        speed="standard",
        board_str="""
0000000000K4Q40000000000
000000000000Q40000000000
000000000000000000000000
000000000000000000000000
000000000000000000000000
Q3Q3000000000000000000K1
K3000000000000000000Q1Q1
000000000000000000000000
000000000000000000000000
000000000000000000000000
0000000000Q2000000000000
0000000000Q2K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Queen's Gambit",
        description="Become the queen of queens.",
    ),
    CampaignLevel(
        level_id=36,
        belt=5,
        speed="standard",
        board_str="""
000000B4B4K4B4B400000000
000000000000000000000000
000000000000000000000000
0000000000000000000000B1
B300000000000000000000B1
B300000000000000000000K1
K300000000000000000000B1
B300000000000000000000B1
B30000000000000000000000
000000000000000000000000
000000000000000000000000
00000000B2B2K2B2B2000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Crossfire",
        description="Position carefully to avoid getting caught in the crossfire.",
    ),
    CampaignLevel(
        level_id=37,
        belt=5,
        speed="standard",
        board_str="""
0000000000K4000000000000
000000B4B4B4B4B4B4000000
000000000000000000000000
00B30000000000000000R100
00B30000000000000000R100
00B30000000000000000R1K1
K3B30000000000000000R100
00B30000000000000000R100
00B30000000000000000R100
000000000000000000000000
000000B2B2B2B2B2B2000000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="The Great Wall",
        description="Hold off the barbarians from your stone fortress!",
    ),
    CampaignLevel(
        level_id=38,
        belt=5,
        speed="standard",
        board_str="""
0000000000K4Q40000000000
0000000000R4R40000000000
0000000000B4B40000000000
0000000000N4N40000000000
000000000000000000000000
Q3R3B3N300000000N1B1R1K1
K3R3B3N300000000N1B1R1Q1
000000000000000000000000
0000000000N2N20000000000
0000000000B2B20000000000
0000000000R2R20000000000
0000000000Q2K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Death Parade",
        description="Will you choose to live?",
    ),
    CampaignLevel(
        level_id=39,
        belt=5,
        speed="standard",
        board_str="""
0000R4N4B4K4Q4B4N4R40000
0000P4P4P4P4P4P4P4P40000
R3P30000000000000000P1R1
N3P30000000000000000P1N1
B3P30000000000000000P1B1
Q3P30000000000000000P1K1
K3P30000000000000000P1Q1
B3P30000000000000000P1B1
N3P30000000000000000P1N1
R3P30000000000000000P1R1
0000P2P2P2P2P2P2P2P20000
0000R2N2B2Q2K2B2N2R20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Grand Melee",
        description="A classic four-player battle. Full armies, no mercy.",
    ),
    # ========== Belt 6: Blue (4P Lightning) ==========
    CampaignLevel(
        level_id=40,
        belt=6,
        speed="lightning",
        board_str="""
0000000000K4000000000000
000000000000000000000000
000000000000000000000000
000000000000000000000000
0000000000000000000000R1
0000000000000000000000K1
K300000000000000000000Q1
000000000000000000000000
000000000000000000000000
000000000000000000000000
000000000000000000000000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="The Thunderdome",
        description="There are no rules except being the last one standing. Bring your best weapons!",
    ),
    CampaignLevel(
        level_id=41,
        belt=6,
        speed="lightning",
        board_str="""
0000000000P4000000000000
00000000P400P40000000000
000000P400K400P4000000R1
00000000P400P40000000000
0000P30000P4000000000000
00P300P300000000000000K1
P300K300P300000000000000
00P300P30000P20000000000
0000P30000P200P200000000
00000000P200K200P20000R1
0000000000P200P200000000
000000000000P20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Gotta Go Fast",
        description="Collect all of the rings and zoom out of there.",
    ),
    CampaignLevel(
        level_id=42,
        belt=6,
        speed="lightning",
        board_str="""
0000B400B4K4B400B4000000
000000000000000000000000
0000000000000000000000R1
R30000000000000000000000
0000000000000000000000B1
R300000000000000000000K1
K300000000000000000000Q1
R300000000000000000000B1
000000000000000000000000
R300000000000000000000R1
000000000000000000000000
000000B200B2K2B200B20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Dodge This!",
        description="In the matrix, bullets are just another obstacle.",
    ),
    CampaignLevel(
        level_id=43,
        belt=6,
        speed="lightning",
        board_str="""
00000000Q4K4Q40000000000
00000000Q4Q4000000000000
000000000000000000000000
000000000000000000000000
000000000000000000000000
Q3Q30000000000000000B1K1
K300000000000000000000R1
Q3Q30000000000000000B100
000000000000000000000000
000000000000000000000000
0000000000Q2Q20000000000
0000000000Q2K2Q200000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Hesitation is Defeat",
        description="A true shinobi knows when to strike for the kill.",
    ),
    CampaignLevel(
        level_id=44,
        belt=6,
        speed="lightning",
        board_str="""
0000N4N4N4K4Q4N4N4N40000
000000000000000000000000
N300000000000000000000N1
N300000000000000000000N1
N300000000000000000000N1
Q300000000000000000000K1
K300000000000000000000Q1
N300000000000000000000N1
N300000000000000000000N1
N300000000000000000000N1
000000000000000000000000
0000N2N2N2Q2K2N2N2N20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Sharingan",
        description="Can your eyes see the future and predict your opponent's moves?",
    ),
    CampaignLevel(
        level_id=45,
        belt=6,
        speed="lightning",
        board_str="""
0000000000K4000000000000
0000000000P4P4P4P4P40000
0000000000Q1Q10000Q1Q100
000000000000000000Q10000
0000000000000000P3Q10000
Q300000000000000P30000K1
K300000000000000P30000Q1
0000000000000000P3Q10000
000000000000000000Q10000
0000000000Q1Q10000Q1Q100
0000000000P2P2P2P2P20000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="'Tis But a Scratch",
        description="A flesh wound is nothing you can't overcome.",
    ),
    CampaignLevel(
        level_id=46,
        belt=6,
        speed="lightning",
        board_str="""
0000000000K4000000000000
000000000000000000000000
00000000P100P100P100P100
000000000000000000000000
0000000000R4B40000000000
00000000B3N40000000000K1
K3000000R3N3N20000000000
0000000000B2R20000000000
000000000000000000000000
00000000P100P100P100P100
000000000000000000000000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Edgerunners",
        description="In Night City, you either run the edge or get edged out.",
    ),
    CampaignLevel(
        level_id=47,
        belt=6,
        speed="lightning",
        board_str="""
0000R4N4B4K4Q4B4N4R40000
0000P4P4P4P4P4P4P4P40000
R3P30000000000000000P1R1
N3P30000000000000000P1N1
B3P30000000000000000P1B1
Q3P30000000000000000P1K1
K3P30000000000000000P1Q1
B3P30000000000000000P1B1
N3P30000000000000000P1N1
R3P30000000000000000P1R1
0000P2P2P2P2P2P2P2P20000
0000R2N2B2Q2K2B2N2R20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Plus Ultra",
        description="Full armies. Lightning speed. Go beyond your limits!",
    ),
    # ========== Belt 7 (4P Standard) ==========
    CampaignLevel(
        level_id=48,
        belt=7,
        speed="standard",
        board_str="""
0000R4N4B4K4Q4B4N4R40000
0000P4P4P4P4P4P4P4P40000
R3P300000000000000000000
N3P300000000000000000000
B3P30000Q1Q1Q1Q1Q1000000
Q3P30000Q1Q1K1Q1Q1000000
K3P30000Q1Q1Q1Q1Q1000000
B3P30000Q1Q1Q1Q1Q1000000
N3P300000000000000000000
R3P300000000000000000000
0000P2P2P2P2P2P2P2P20000
0000R2N2B2Q2K2B2N2R20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Domain Expansion",
        description="Turn reality into your playground.",
    ),
    CampaignLevel(
        level_id=49,
        belt=7,
        speed="standard",
        board_str="""
0000000000K4000000000000
0000R400R40000R400R40000
00R300000000000000000000
00000000000000000000N1N1
00R30000000000000000N1N1
000000000000K1000000N1N1
K3000000000000000000N1N1
00R30000000000000000N1N1
00000000000000000000N1N1
00R300000000000000000000
0000R200R20000R200R20000
000000000000K20000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="The Cavalry Has Arrived",
        description="Just when you thought all hope was lost, reinforcements arrive to turn the tide of battle.",
    ),
    CampaignLevel(
        level_id=50,
        belt=7,
        speed="standard",
        board_str="""
0000B10000K400B100000000
000000P4P4P4P4P400B10000
00N100000000000000000000
000000000000000000000000
N1P300000000000000000000
00P3000000000000000000K1
K3P300000000000000000000
00P300000000000000000000
00P300000000000000000000
N10000000000000000000000
0000R100P2P2P2P2P2000000
000000000000K20000R10000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Behind Enemy Lines",
        description="Your agents have infiltrated the enemy's position.",
    ),
    CampaignLevel(
        level_id=51,
        belt=7,
        speed="standard",
        board_str="""
000000000000000000000000
000000000000000000000000
0000000000R4R40000000000
0000000000K4Q40000000000
0000000000000000K1R10000
0000000000000000Q1R10000
0000R3Q30000000000000000
0000R3K30000000000000000
0000000000Q2K20000000000
0000000000R2R20000000000
000000000000000000000000
000000000000000000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="The Crucible",
        description="Four armies collide in the center. There is no retreat.",
    ),
    CampaignLevel(
        level_id=52,
        belt=7,
        speed="standard",
        board_str="""
0000000000K4000000000000
000000B4B4B4B4B4B4000000
000000000000000000000000
00B30000P1P1P1P1P1000000
00B30000P1P1P1P1P1000000
00B30000P1P1K1P1P1000000
K3B30000P1P1P1P1P1000000
00B30000P1P1P1P1P1000000
00B300000000000000000000
000000000000000000000000
000000B2B2B2B2B2B2000000
0000000000K2000000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Get Down, Mr. President!",
        description="Keep your bodyguards close and your king safe.",
    ),
    CampaignLevel(
        level_id=53,
        belt=7,
        speed="standard",
        board_str="""
0000000000Q1Q10000000000
000000000000000000000000
000000000000000000000000
000000Q4Q4Q4000000000000
000000Q4K4Q400K100000000
Q10000Q4Q4Q40000000000Q1
Q10000Q3Q3Q3Q2Q2Q20000Q1
000000Q3K3Q3Q2K2Q2000000
000000Q3Q3Q3Q2Q2Q2000000
000000000000000000000000
000000000000000000000000
0000000000Q1Q10000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Oppenheimer",
        description="Can you wield the power of the atom without destroying yourself?",
    ),
    CampaignLevel(
        level_id=54,
        belt=7,
        speed="standard",
        board_str="""
00000000B4K4Q40000R40000
0000P4P4P4P4P4P4P4P40000
R3P3000000000000000000R1
N3P3000000000000000000N1
B3P3000000000000000000B1
Q3P300000000000000000000
K3P3000000000000000000Q1
B3P3000000000000000000B1
N3P3000000000000000000N1
K1P3000000000000000000R1
0000P2P2P2P2P2P2P2P20000
0000R20000Q2K2B200000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Hidden In Plain Sight",
        description="Survive in the heart of the enemy's territory until the dust settles.",
    ),
    CampaignLevel(
        level_id=55,
        belt=7,
        speed="standard",
        board_str="""
0000P40000P400P400P30000
0000P20000P400P400P30000
P3P3P1P100P200P200P200P4
0000000000P200P200P200P2
P3P3P1P1K1P1P400K3000000
000000000000P400P400P3P1
P3P3P1P10000P200P200Q100
00000000K400P200K20000P1
P400P400P4000000P20000P4
P200P400P400P3P3P1P100P2
0000P200P200000000000000
0000P200P200P3P3P1P10000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Infinity Castle",
        description="Navigate the endless corridors and find your way to the throne room at the center.",
    ),
    # ========== Belt 8: Red (2P Lightning) ==========
    CampaignLevel(
        level_id=56,
        belt=8,
        speed="lightning",
        board_str="""
00R20000K20000R2
0000000000000000
00N1000000N10000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
R1000000K10000R1
""",
        title="Omae Wa Mou Shindeiru",
        description="You are already dead. You just don't know it yet.",
    ),
    CampaignLevel(
        level_id=57,
        belt=8,
        speed="lightning",
        board_str="""
B200B200K200B2B2
0000000000000000
P100P1P100P1P100
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00000000K1000000
""",
        title="This Isn't Even My Final Form",
        description="Transform your pawns before the bishops clip their wings.",
    ),
    CampaignLevel(
        level_id=58,
        belt=8,
        speed="lightning",
        board_str="""
K20000000000K100
R20000000000P100
R200000000P10000
R2000000P1000000
R20000P1P1P1P100
R200000000P10000
R2000000P1000000
R20000P100000000
""",
        title="Dancing Through the Lightning Strikes",
        description="But now, the sky is opalite.",
    ),
    CampaignLevel(
        level_id=59,
        belt=8,
        speed="lightning",
        board_str="""
Q1P2P2P2K2P2P2P2
P2P2P2P2P2P2P2P2
P2P2P2P2P2P2P2P2
0000000000000000
0000000000000000
0000000000000000
0000000000000000
00000000K1000000
""",
        title="LEEEROY JENKINSSS!!!",
        description="Sometimes, you just gotta charge in and hope for the best.",
    ),
    CampaignLevel(
        level_id=60,
        belt=8,
        speed="lightning",
        board_str="""
B200B200K200B200
0000B20000B20000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
0000000000000000
R1R10000K100R1R1
""",
        title="Power of Parity",
        description="Pay attention to the color of squares as you move. It might just save your life.",
    ),
    CampaignLevel(
        level_id=61,
        belt=8,
        speed="lightning",
        board_str="""
000000P2K2000000
0000P20000P20000
00P200000000P200
P2000000000000P2
00P200000000P200
0000P20000P20000
00000000P2000000
Q1000000K10000Q1
""",
        title="Do a Barrel Roll",
        description="Use the boost to get through!",
    ),
    CampaignLevel(
        level_id=62,
        belt=8,
        speed="lightning",
        board_str="""
R1N1B1Q1K1B1N1R1
P1P1P1P1P1P1P1P1
0000000000000000
0000000000000000
0000000000000000
0000000000000000
P2P2P2P2P2P2P2P2
R2N2B2Q2K2B2N2R2
""",
        title="Mirror's Edge",
        description="Something seems off about this place...",
    ),
    CampaignLevel(
        level_id=63,
        belt=8,
        speed="lightning",
        board_str="""
00000000000000K1
P200000000000000
P1P20000P2000000
00P1P200P1P20000
0000P1P200P1P200
000000P10000P1P2
00000000000000P1
K200000000000000
""",
        title="Psycho Pass",
        description="Can you trust the Sibyl system with the fate of humanity?",
    ),
    # ========== Belt 9: Black (4P Lightning) ==========
    CampaignLevel(
        level_id=64,
        belt=9,
        speed="lightning",
        board_str="""
000000000000000000000000
000000000000000000000000
00000000K400000000000000
00000000P400000000000000
00000000000000P1P1000000
K3P3000000000000K1000000
00000000000000P1P1000000
000000000000000000000000
00000000P200000000000000
00000000K200000000000000
000000000000000000000000
000000000000000000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="One Punch Man",
        description="Consecutive normal punches should do the trick. Just don't miss.",
    ),
    CampaignLevel(
        level_id=65,
        belt=9,
        speed="lightning",
        board_str="""
0000P4P4P4K4P4P4P4P40000
0000P4P4P4P4P4P4P4P40000
P3P300P4P4P4P4P4P400P1P1
P3P3P300P4P4P4P400P1P1P1
P3P3P3P300P4P400P1P1P1P1
P3P3P3P3P30000P1P1P1P1K1
K3P3P3P3P30000P1P1P1P1P1
P3P3P3P300P2P200P1P1P1P1
P3P3P300P2P2P2P200P1P1P1
P3P300P2P2P2P2P2P200P1P1
0000P2P2P2P2P2P2P2P20000
0000P2P2P2P2K2P2P2P20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Squid Game",
        description="456 players enter, but only one wins.",
    ),
    CampaignLevel(
        level_id=66,
        belt=9,
        speed="lightning",
        board_str="""
0000Q2Q2Q2Q2K2B2R2Q20000
0000P2P2P2P2P2P2P2P20000
00000000000000000000P3Q3
00000000000000000000P3Q3
B1000000000000000000P3Q3
00000000000000000000P3K3
K1000000000000000000P3B3
00000000000000000000P3R3
B1000000000000000000P3Q3
00000000000000000000P3Q3
0000P4P4P4P4P4P4P4P40000
0000Q4R4B4K4Q4Q4Q4Q40000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Survey Corps",
        description="Danger lies beyond the walls. Attack the giant targets with precision!",
    ),
    CampaignLevel(
        level_id=67,
        belt=9,
        speed="lightning",
        board_str="""
0000Q4K4Q400000000000000
0000Q4Q4Q4000000R1000000
0000Q4Q4Q400000000B10000
0000000000000000R1B1R100
000000000000000000B10000
Q3Q3Q30000000000R10000K1
K3Q3Q3000000R100000000Q1
Q3Q3Q300000000B100000000
000000000000R1B1R1000000
0000Q2Q2Q20000B100000000
0000Q2Q2Q200R10000000000
0000Q2K2Q200000000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Golden",
        description="We're goin' up, up, up, it's our moment.",
    ),
    CampaignLevel(
        level_id=68,
        belt=9,
        speed="lightning",
        board_str="""
000000000000000000000000
000000000000000000000000
0000P4P1P1P1P1P1P1P10000
0000P4000000000000P20000
0000P400K4P1P1K100P20000
0000P400P40000P200P20000
0000P400P40000P200P20000
0000P400K3P3P3K200P20000
0000P4000000000000P20000
0000P3P3P3P3P3P3P3P20000
000000000000000000000000
000000000000000000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Inception",
        description="Is this the real world, or just a dream within a dream?",
    ),
    CampaignLevel(
        level_id=69,
        belt=9,
        speed="lightning",
        board_str="""
0000Q4P400K40000P4Q40000
000000P400P40000P4000000
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
P4P400P400P40000P400P4P4
000000P400P40000P4000000
000000K300K1Q100K2000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="I'm Blue",
        description="Da ba dee da ba daa, da ba dee da ba daa.",
    ),
    CampaignLevel(
        level_id=70,
        belt=9,
        speed="lightning",
        board_str="""
0000B4B400K400B4B4000000
00000000B400B40000000000
000000000000000000000000
R3R3000000000000000000B1
0000000000000000000000N1
R3000000000000000000R1K1
K300000000000000000000Q1
R30000000000000000000000
000000000000000000000000
R3R300000000000000000000
0000000000N200N200000000
000000N2N200K200N2N20000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="The Last Airbender",
        description="Water. Earth. Fire. Air. Only the Avatar can master all four elements.",
    ),
    CampaignLevel(
        level_id=71,
        belt=9,
        speed="lightning",
        board_str="""
000000000000000000000000
000000000000000000000000
K4Q4Q400000000B1B1B10000
Q4Q4Q4000000B1B100000000
Q3Q3000000B100B100000000
K3Q30000B10000K100000000
Q3Q3000000B100B100000000
Q2Q2Q2000000B1B100000000
K2Q2Q200000000B1B1B10000
000000000000000000000000
000000000000000000000000
000000000000000000000000
""",
        board_type=BoardType.FOUR_PLAYER,
        player_count=4,
        title="Endgame",
        description="End it all with a snap of your fingers.",
    ),
]


def get_level(level_id: int) -> CampaignLevel | None:
    """Get a level by ID."""
    if 0 <= level_id < len(LEVELS):
        return LEVELS[level_id]
    return None


def get_belt_levels(belt: int) -> list[CampaignLevel]:
    """Get all levels for a belt (8 levels per belt)."""
    start = (belt - 1) * 8
    end = start + 8
    return [lvl for lvl in LEVELS if start <= lvl.level_id < end]
