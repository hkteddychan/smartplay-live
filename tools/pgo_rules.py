"""Competition rules for the PGSharp internal closed-beta bot.

Hard constraints (set by the user, 2026-11-01):

R1  絕不可以用「超級球」 (Great Ball)
R2  絕不可以餵「金色提子」 (Golden Razz Berry)
R3  捕捉只能用「精靈球」(Poké Ball) 或「高級球」(Ultra Ball)；
    高級球不在禁用清單內，但仍預設使用精靈球。
R4  設定頁的「自動投食」只會用 蔓莓果 / 蕉香果 / 凰梨果，
    本身不會用到金色提子；但我們一律不做「手動餵食」。
R5  絕不進入、絕不參與任何「團體戰 / 極巨化 / 對戰 / Raid / Max Battle」
    （2026-11-02 由使用者指示）。遇到團體戰畫面只可按 X 離開。

The bot enforces these at the point of action, not just in documentation:
`assert_ball_allowed()` is called before every throw and `assert_berry_allowed()`
before every manual feed.
"""
from __future__ import annotations

# Balls, keyed by the Chinese label the client shows.
BALLS = {
    "精靈球": "pokeball",
    "超級球": "greatball",
    "高級球": "ultraball",
}

# R1 - never throw a Great Ball.
BANNED_BALLS = {"超級球", "greatball"}

# R2 - never feed a Golden Razz.
BANNED_BERRIES = {"金色提子", "golden_razz", "goldenrazz"}

# Berries the client is allowed to auto-feed (R4).
ALLOWED_AUTO_BERRIES = {"蔓莓果", "蕉香果", "凰梨果"}

# Ball the bot will explicitly select when it opens the tray.
DEFAULT_BALL = "精靈球"

# Throw quality targets enabled in PGSharp > 設置 > 增強丟球.
ALLOWED_THROW_RATINGS = {"Great", "Excellent", "曲球"}


class RuleViolation(RuntimeError):
    pass


# R5 - never join a raid / max battle.  Any action that would start one is
# refused before it reaches the device.
RAID_STATES = {"raid", "max_battle", "gym_battle"}
RAID_START_LABELS = {"對戰", "使用250MP", "私人小組", "加入對戰", "Battle"}


def assert_no_raid(state: str) -> str:
    if state in RAID_STATES:
        raise RuleViolation(f"R5 violation: 團體戰 is forbidden (state={state!r})")
    return state


def is_raid_label(text: str) -> bool:
    return text in RAID_START_LABELS


def assert_ball_allowed(ball: str) -> str:
    if ball in BANNED_BALLS:
        raise RuleViolation(f"R1 violation: 超級球 (Great Ball) is forbidden (got {ball!r})")
    return ball


def assert_berry_allowed(berry: str) -> str:
    if berry in BANNED_BERRIES:
        raise RuleViolation(f"R2 violation: 金色提子 is forbidden (got {berry!r})")
    return berry


def is_allowed_ball(ball: str) -> bool:
    return ball not in BANNED_BALLS


def describe() -> str:
    return (
        "R1 禁用 超級球(Great Ball)\n"
        "R2 禁用 金色提子(Golden Razz)\n"
        f"R3 可用球: 精靈球 / 高級球   預設: {DEFAULT_BALL}\n"
        "R4 自動投食只含 蔓莓果/蕉香果/凰梨果；不做手動餵食\n"
        "R5 絕不進入/參與任何團體戰（對戰 / 極巨化 / Raid）"
    )
