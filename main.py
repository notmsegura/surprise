import json
from dataclasses import asdict, dataclass
from drafter import *
from js import localStorage

# -----------------------------------------------------------------------------
# Data Models (Isolated Category State & Persistable Dataclasses)
# -----------------------------------------------------------------------------
CATEGORIES = [
    "Apologetics, Junior",
    "Apologetics, Senior",
    "Impromptu, Junior",
    "Impromptu, Senior",
    "Prepared, Junior",
    "Prepared, Senior",
]


@dataclass
class Ballot:
    judge_name: str
    ranks: dict[str, float]
    is_official: bool = True


@dataclass
class State:
    # Each category gets its own independent list instance initialized on startup
    ballots: dict[str, list[Ballot]] = None
    current_category: str = ""
    input_judge_name: str = ""
    input_ranks_text: str = ""
    input_is_official: bool = True
    form_message: str = ""

    def __post_init__(self):
        if self.ballots is None:
            self.ballots = {cat: [] for cat in CATEGORIES}


# -----------------------------------------------------------------------------
# LocalStorage Persistence Helpers
# -----------------------------------------------------------------------------
STORAGE_KEY = "speech_competition_state"


def save_state(state: State):
    """Serializes the State dataclass (including nested Ballots) and saves to browser storage."""
    state_dict = asdict(state)
    localStorage.setItem(STORAGE_KEY, json.dumps(state_dict))


def load_state() -> State:
    """Retrieves state from browser storage and reconstructs State and Ballot objects."""
    saved_json = localStorage.getItem(STORAGE_KEY)
    if not saved_json:
        return State()

    try:
        data = json.loads(saved_json)

        # Reconstruct Ballot objects inside the nested category dict
        raw_ballots = data.get("ballots", {})
        reconstructed_ballots = {}

        for cat in CATEGORIES:
            cat_ballots = raw_ballots.get(cat, [])
            reconstructed_ballots[cat] = [
                Ballot(
                    judge_name=b["judge_name"],
                    ranks=b["ranks"],
                    is_official=b.get("is_official", True),
                )
                for b in cat_ballots
            ]

        data["ballots"] = reconstructed_ballots
        return State(**data)
    except Exception:
        # Fallback to fresh State if stored data structure is corrupted
        return State()


# -----------------------------------------------------------------------------
# Helper Functions (Scoring Logic & Unit-Tested Parsers)
# -----------------------------------------------------------------------------
def parse_ranks(ranks_text: str) -> tuple[dict[str, float], str]:
    """Parses contestant ranks and checks for duplicate names or ranks."""
    result = {}
    seen_ranks = set()
    items = ranks_text.split(",")

    for item in items:
        item = item.strip()
        if not item:
            continue

        parts = item.rsplit(" ", 1)
        if len(parts) == 2:
            name, rank_str = parts[0].strip().title(), parts[1].strip()
            clean_rank = "".join(
                ch for ch in rank_str if ch.isdigit() or ch == "."
            )

            if clean_rank:
                rank_val = float(clean_rank)

                if name in result:
                    return {}, f"⚠️ Duplicate name '{name}' found in the ballot!"

                if rank_val in seen_ranks:
                    return (
                        {},
                        f"⚠️ Rank {int(rank_val)} assigned to multiple people!",
                    )

                result[name] = rank_val
                seen_ranks.add(rank_val)

    return result, ""


def calculate_standings(ballots: list[Ballot]) -> list[tuple[str, float]]:
    """Calculates average rank per contestant for a specific list of ballots."""
    scores = {}
    counts = {}

    for ballot in ballots:
        for contestant, rank in ballot.ranks.items():
            scores[contestant] = scores.get(contestant, 0.0) + rank
            counts[contestant] = counts.get(contestant, 0) + 1

    averages = []
    for contestant, total in scores.items():
        avg = total / counts[contestant]
        averages.append((contestant, round(avg, 2)))

    averages.sort(key=lambda x: x[1])
    return averages


# -----------------------------------------------------------------------------
# Home & Navigation Routes
# -----------------------------------------------------------------------------
@route
def index(state: State) -> Page:
    """Home Page containing category selection buttons and global reset."""
    return Page(
        state,
        [
            Header("Speech Competition Scoring System", level=1),
            Text("Select a category to manage ballots and standings:"),
            *[
                Button(cat, select_category, [Argument("category", cat)])
                for cat in CATEGORIES
            ],
            Button("Clear All Stored Data", reset_all_data),
        ],
    )


@route
def select_category(state: State, category: str = "") -> Page:
    """Route handler for setting current category from index."""
    if category:
        state.current_category = category
    state.form_message = ""
    state.input_judge_name = ""
    state.input_ranks_text = ""
    state.input_is_official = True
    save_state(state)
    return category_menu_page(state)


@route
def go_to_category_menu(state: State) -> Page:
    """Helper route to return to category dashboard safely."""
    return category_menu_page(state)


def category_menu_page(state: State) -> Page:
    """Renders the main dashboard for the active category."""
    category = state.current_category
    ballot_count = len(state.ballots.get(category, []))

    return Page(
        state,
        [
            Button("← Back to Home", index),
            Header(f"{category} Dashboard", level=1),
            Text(f"Total Ballots Submitted: {ballot_count}"),
            Button("View Standings", show_standings),
            Button("Input Ballot", show_input_ballot_form),
            Button("Remove Ballots", show_remove_ballots_page),
        ],
    )


# -----------------------------------------------------------------------------
# 1. View Standings Page
# -----------------------------------------------------------------------------
@route
def show_standings(state: State) -> Page:
    """Displays standings strictly for the current category."""
    category = state.current_category
    category_ballots = state.ballots.get(category, [])
    standings = calculate_standings(category_ballots)

    content = [
        Button(f"← Back to {category}", go_to_category_menu),
        Header(f"Standings — {category}", level=1),
    ]

    if not standings:
        content.append(
            Text(
                "No ballots have been submitted for this category yet.",
                italic=True,
            )
        )
    else:
        formatted_items = []
        current_rank = 1

        for i, (name, avg_score) in enumerate(standings):
            if i > 0 and avg_score == standings[i - 1][1]:
                pass
            else:
                current_rank = i + 1

            formatted_items.append(f"#{current_rank} — {name}")

        standings_formatted = ", ".join(formatted_items)
        content.append(Text(standings_formatted))

    return Page(state, content)


# -----------------------------------------------------------------------------
# 2. Input Ballot Page & Submission Handler
# -----------------------------------------------------------------------------
@route
def show_input_ballot_form(state: State) -> Page:
    """Renders ballot entry form."""
    category = state.current_category

    return Page(
        state,
        [
            Button(f"← Back to {category}", go_to_category_menu),
            Header(f"Input Ballot — {category}", level=1),
            Text("Judge Name:"),
            TextBox("input_judge_name", default_value=state.input_judge_name),
            Text(
                "Enter Ranks (Comma-separated, e.g. 'Joey Miller 1st, Johnny Depp 2nd'):"
            ),
            TextBox("input_ranks_text", default_value=state.input_ranks_text),
            CheckBox(
                "input_is_official",
                default_value=state.input_is_official,
                label="Mark as Official Round Ballot",
            ),
            Button("Submit Ballot", submit_ballot),
            Text(state.form_message, bold=True),
        ],
    )


@route
def submit_ballot(
    state: State,
    input_judge_name: str = "",
    input_ranks_text: str = "",
    input_is_official: bool = True,
) -> Page:
    """Processes submitted ballot data and persists changes."""
    category = state.current_category

    if category not in CATEGORIES:
        state.form_message = "⚠️ No category selected."
        return show_input_ballot_form(state)

    parsed_ranks, error = parse_ranks(input_ranks_text)

    if not input_judge_name.strip():
        state.form_message = "⚠️ Please enter a valid Judge Name."
        return show_input_ballot_form(state)

    if error:
        state.form_message = error
        return show_input_ballot_form(state)

    if not parsed_ranks:
        state.form_message = (
            "⚠️ Please enter valid ranks (e.g. 'Joey 1st, Johny 2nd')."
        )
        return show_input_ballot_form(state)

    new_ballot = Ballot(
        judge_name=input_judge_name.strip(),
        ranks=parsed_ranks,
        is_official=input_is_official,
    )

    state.ballots[category].append(new_ballot)

    state.input_judge_name = ""
    state.input_ranks_text = ""
    state.input_is_official = True
    state.form_message = (
        f"✓ Ballot by Judge {new_ballot.judge_name} submitted successfully!"
    )

    # PERSISTENCE: Save state after successful write action
    save_state(state)

    return show_input_ballot_form(state)


# -----------------------------------------------------------------------------
# 3. Remove Ballots Page, Direct Deletion & System Reset
# -----------------------------------------------------------------------------
@route
def show_remove_ballots_page(state: State) -> Page:
    """Renders ballot deletion list for the active category."""
    category = state.current_category
    category_ballots = state.ballots.get(category, [])

    content = [
        Button(f"← Back to {category}", go_to_category_menu),
        Header(f"Remove Ballots — {category}", level=1),
    ]

    if not category_ballots:
        content.append(Text("There are no ballots to remove.", italic=True))
    else:
        for idx, ballot in enumerate(category_ballots):
            ranks_str = ", ".join(
                f"{k}: {int(v) if v.is_integer() else v}"
                for k, v in ballot.ranks.items()
            )
            status_str = "Official" if ballot.is_official else "Practice"
            content.append(
                Text(
                    f"Judge: {ballot.judge_name} [{status_str}] | Ranks: {ranks_str}"
                )
            )
            content.append(
                Button(
                    f"Delete Ballot #{idx + 1}",
                    delete_ballot,
                    [Argument("index", idx)],
                )
            )

    return Page(state, content)


@route
def delete_ballot(state: State, index: int = -1) -> Page:
    """Deletes targeted ballot and updates browser storage."""
    category = state.current_category

    if category in state.ballots and 0 <= index < len(state.ballots[category]):
        del state.ballots[category][index]
        save_state(state)

    return show_remove_ballots_page(state)


@route
def reset_all_data(state: State) -> Page:
    """Clears browser localStorage and resets state to blank defaults."""
    localStorage.removeItem(STORAGE_KEY)
    fresh_state = State()
    return index(fresh_state)


# -----------------------------------------------------------------------------
# Unit Tests
# -----------------------------------------------------------------------------
def run_unit_tests():
    """Runs automated unit test assertions for core helper functions."""
    ranks, err = parse_ranks("Joey 1st, Johnny 2nd")
    assert ranks == {"Joey": 1.0, "Johnny": 2.0}
    assert err == ""

    ranks, err = parse_ranks("Joey 1st, Joey 2nd")
    assert ranks == {}
    assert "Duplicate name" in err

    b1 = Ballot("Judge A", {"Joey": 1.0, "Johnny": 2.0})
    b2 = Ballot("Judge B", {"Joey": 3.0, "Johnny": 1.0})
    standings = calculate_standings([b1, b2])
    assert standings == [("Johnny", 1.5), ("Joey", 2.0)]

    s = State()
    s.ballots["Prepared, Junior"].append(Ballot("Judge A", {"Joey": 1.0}))
    assert len(s.ballots["Prepared, Senior"]) == 0
    assert calculate_standings(s.ballots["Prepared, Senior"]) == []
    assert len(s.ballots["Prepared, Junior"]) == 1


run_unit_tests()

# -----------------------------------------------------------------------------
# App Start & Deployment Metadata
# -----------------------------------------------------------------------------
set_site_information(
    "Matthew Segura CISC106",
    "Speech Competition Scoring System",
    "Calculates average competitor rankings across categories.",
    "CISC 106",
    "Speech competition ballot scoring system planning document",
)

# Start server initialized with saved data from browser storage
start_server(load_state())
