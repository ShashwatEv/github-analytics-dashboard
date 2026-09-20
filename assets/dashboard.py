import pandas as pd
import squarify
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import MaxNLocator
import logging
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))
from palettes import THEMES, DEFAULT_THEME

logger = logging.getLogger(__name__)

# Only filter out languages if they crowd your view. Kept empty by default.
FILTERED_LANGS = set()

STAGE_ORDER = ["Live", "In progress", "Stub", "Archived"]


def format_relative_date(val) -> str:
    """Format timestamps or dates into clean human-readable strings."""
    if pd.isna(val) or val is None or val == 0:
        return "recently"
    try:
        ts = pd.to_datetime(val)
        # Guard against Unix epoch default (1970)
        if ts.year <= 1970:
            return "recently"

        now = pd.Timestamp.now(tz=ts.tz) if ts.tz else pd.Timestamp.now()
        days_ago = (now - ts).days
        if days_ago <= 0:
            return "today"
        if days_ago == 1:
            return "yesterday"
        if days_ago < 30:
            return f"{days_ago}d ago"
        if days_ago < 365:
            return f"{days_ago // 30}mo ago"
        return f"{days_ago // 365}y ago"
    except Exception:
        return "recently"


def create_dashboard(df: pd.DataFrame, output_path: str = "github_dashboard.svg", theme: str = DEFAULT_THEME):
    T = THEMES.get(theme, THEMES[DEFAULT_THEME])
    BG, PANEL, CARD, BORDER = T["bg"], T["panel"], T["card"], T["border"]
    TEXT, TEXT_MUTED = T["text"], T["muted"]
    HERO, C2, C3, C4, C5 = T["hero"], T["c2"], T["c3"], T["c4"], T["c5"]
    ACCENT, PRIVATE = T["accent"], T["private"]
    RAMP = [HERO, C2, C3, C4, C5]
    STAGE_COLORS = {
        "Live": ACCENT, "In progress": HERO, "Stub": C5, "Archived": C4,
    }

    plt.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": BORDER,
        "axes.labelcolor": TEXT,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
        "text.color": TEXT,
        "grid.color": BORDER,
        "axes.titleweight": "bold",
        "font.size": 10,
        "font.family": "sans-serif",
    })

    df = df.copy()

    total_repos = len(df)
    total_stars = int(df["stars"].sum()) if "stars" in df.columns else 0
    languages_used = int(df["language"].nunique()) if "language" in df.columns else 0
    active_repos = int(df["is_active"].sum()) if "is_active" in df.columns else 0
    private_repos = int(df["private"].sum()) if "private" in df.columns else 0
    public_repos = total_repos - private_repos

    # Cumulative growth dataset
    repos_per_year = (
        df.groupby("year_created")
        .size()
        .reset_index(name="count")
        .sort_values("year_created")
    )
    repos_per_year["cumulative"] = repos_per_year["count"].cumsum()
    current_year = pd.Timestamp.now(tz="UTC").year

    # Language composition
    if "language" in df.columns:
        lang_counts = (
            df[df["language"].notna()]
            .groupby("language")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        lang_counts = lang_counts[~lang_counts["language"].isin(FILTERED_LANGS)].head(10)
    else:
        lang_counts = pd.DataFrame(columns=["language", "count"])

    stage_counts = (
        df["stage"].value_counts().reindex(STAGE_ORDER).dropna().astype(int)
        if "stage" in df.columns else pd.Series(dtype=int)
    )

    fig = plt.figure(figsize=(20, 15), facecolor=BG)
    gs = fig.add_gridspec(
        4, 6,
        height_ratios=[0.7, 2.0, 1.7, 0.45],
        hspace=0.55, wspace=0.35,
        top=0.92, bottom=0.05, left=0.05, right=0.95,
    )

    def create_stat_tile(ax, value, label, color):
        ax.axis("off")
        rect = FancyBboxPatch((0.08, 0.15), 0.84, 0.7,
                               boxstyle="round,pad=0.08",
                               facecolor=CARD, edgecolor=color,
                               linewidth=2.5, transform=ax.transAxes)
        ax.add_patch(rect)
        ax.text(0.5, 0.55, str(value), ha="center", va="center",
                fontsize=32, weight="bold", color=color, transform=ax.transAxes)
        ax.text(0.5, 0.26, label, ha="center", va="center",
                fontsize=11, color=TEXT_MUTED, weight="600", transform=ax.transAxes)

    # Top KPI cards
    stat_gs = gs[0, :].subgridspec(1, 4, wspace=0.25)
    create_stat_tile(fig.add_subplot(stat_gs[0]), total_repos, "TOTAL REPOS", HERO)
    create_stat_tile(fig.add_subplot(stat_gs[1]), total_stars, "TOTAL STARS", C2)
    create_stat_tile(fig.add_subplot(stat_gs[2]), active_repos, "ACTIVE REPOS", ACCENT)
    create_stat_tile(fig.add_subplot(stat_gs[3]), languages_used, "LANGUAGES USED", C3)

    # --- Language composition treemap -------------------------------------
    ax_tree = fig.add_subplot(gs[1, 0:4])
    ax_tree.axis("off")
    if len(lang_counts):
        sizes = lang_counts["count"].tolist()
        total_n = sum(sizes)
        colors = [RAMP[i % len(RAMP)] for i in range(len(sizes))]
        labels = [
            f"{lang}\n{count / total_n * 100:.0f}%"
            for lang, count in zip(lang_counts["language"], lang_counts["count"])
        ]
        squarify.plot(
            sizes=sizes, label=labels, color=colors, ax=ax_tree,
            pad=True, text_kwargs={"fontsize": 12, "weight": "600", "color": BG},
        )
    ax_tree.set_title("Language Composition", fontsize=15, pad=15, weight="bold", color=TEXT)

    # --- Lifecycle donut --------------------------------------------------
    ax_donut = fig.add_subplot(gs[1, 4:6])
    if len(stage_counts) and stage_counts.sum() > 0:
        colors = [STAGE_COLORS.get(s, C5) for s in stage_counts.index]
        wedges, _ = ax_donut.pie(
            stage_counts.values,
            colors=colors,
            startangle=90,
            wedgeprops=dict(width=0.42, edgecolor=BG, linewidth=2),
        )
        ax_donut.text(0, 0, str(total_repos), ha="center", va="center",
                      fontsize=30, weight="bold", color=TEXT)
        ax_donut.text(0, -0.22, "REPOS", ha="center", va="center",
                      fontsize=11, weight="600", color=TEXT_MUTED)
        legend_labels = [f"{s} ({stage_counts[s]})" for s in stage_counts.index]
        ax_donut.legend(
            wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
            frameon=False, fontsize=11, labelcolor=TEXT,
        )
    ax_donut.set_title("Lifecycle", fontsize=15, pad=15, weight="bold", color=TEXT)

    # --- Cumulative growth curve ------------------------------------------
    ax_growth = fig.add_subplot(gs[2, 0:3])
    ax_growth.plot(
        repos_per_year["year_created"], repos_per_year["cumulative"],
        marker="o", linewidth=3.5, markersize=9, color=HERO,
        markerfacecolor=HERO, markeredgecolor=BG, markeredgewidth=2,
    )
    ax_growth.fill_between(
        repos_per_year["year_created"], repos_per_year["cumulative"],
        alpha=0.2, color=HERO,
    )
    title = "Cumulative Repositories"
    if current_year in repos_per_year["year_created"].values:
        title += f" (note: {current_year} is year to date)"
    ax_growth.set_title(title, fontsize=15, pad=15, weight="bold", color=TEXT)
    ax_growth.set_xlabel("Year", fontsize=11, weight="600")
    ax_growth.set_ylabel("Total repos", fontsize=11, weight="600")
    ax_growth.grid(alpha=0.2, linestyle="--")

    # Enforce clean integer ticks
    ax_growth.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax_growth.yaxis.set_major_locator(MaxNLocator(integer=True))

    # --- Leaderboard / Active Repositories -------------------------------
    ax_lead = fig.add_subplot(gs[2, 3:6])
    ax_lead.axis("off")
    ax_lead.set_xlim(0, 1)
    ax_lead.set_ylim(0, 1)

    use_stars = total_stars > 0
    if use_stars:
        lead_title = "Leaderboard: Most Starred"
        top_repos = df.nlargest(5, "stars")[["name", "stars", "url"]].reset_index(drop=True)
        col_header = "Stars"
    else:
        lead_title = "Active Repositories (Recent Activity)"
        # Pick the most granular available activity column
        sort_col = None
        for candidate in ["pushed_at", "updated_at", "created_at"]:
            if candidate in df.columns and df[candidate].notna().any():
                sort_col = candidate
                break
        if not sort_col:
            sort_col = "year_created" if "year_created" in df.columns else df.columns[0]

        valid_df = df[df[sort_col].notna()] if sort_col in df.columns else df
        top_repos = valid_df.sort_values(sort_col, ascending=False).head(5)[["name", sort_col, "url"]].reset_index(drop=True)
        col_header = "Active"

    header_y = 0.90
    ax_lead.text(0.04, header_y, "Repo", fontsize=13, weight="bold", color=TEXT_MUTED)
    ax_lead.text(0.96, header_y, col_header, fontsize=13, weight="bold", color=TEXT_MUTED, ha="right")
    ax_lead.plot([0.04, 0.96], [header_y - 0.06, header_y - 0.06], color=BORDER, linewidth=1.5)

    row_height = 0.17
    start_y = header_y - 0.16
    for i, row in top_repos.iterrows():
        y = start_y - i * row_height
        if i > 0:
            ax_lead.plot([0.04, 0.96], [y + 0.09, y + 0.09], color=BORDER, linewidth=0.5, alpha=0.3)
        rank_color = RAMP[i % len(RAMP)]
        ax_lead.text(0.04, y, f"{i + 1}", fontsize=13, weight="700", color=rank_color, va="center")
        ax_lead.text(0.11, y, str(row["name"])[:26], fontsize=13, weight="600", color=TEXT, va="center")

        if use_stars:
            metric_str = f"★ {int(row['stars'])}"
        else:
            metric_str = format_relative_date(row[sort_col])
        ax_lead.text(0.96, y, metric_str, fontsize=12, weight="600", color=HERO, va="center", ha="right")

    ax_lead.set_title(lead_title, fontsize=15, pad=15, weight="bold", color=TEXT)

    # --- Visibility & Summary Bar -----------------------------------------
    ax_comp = fig.add_subplot(gs[3, :])
    ax_comp.axis("off")
    ax_comp.set_xlim(0, 1)
    ax_comp.set_ylim(0, 1)

    if total_repos > 0:
        pub_ratio = public_repos / total_repos
        priv_ratio = private_repos / total_repos

        # Public bar
        ax_comp.barh(0.5, pub_ratio, left=0.0, height=0.5, color=ACCENT, edgecolor=BG, linewidth=1.5)
        if pub_ratio > 0.08:
            ax_comp.text(pub_ratio / 2, 0.5, f"Public ({public_repos})", ha="center", va="center",
                         fontsize=10, weight="700", color=BG)

        # Private bar
        if priv_ratio > 0:
            ax_comp.barh(0.5, priv_ratio, left=pub_ratio, height=0.5, color=PRIVATE, edgecolor=BG, linewidth=1.5)
            if priv_ratio > 0.08:
                ax_comp.text(pub_ratio + (priv_ratio / 2), 0.5, f"Private ({private_repos})",
                             ha="center", va="center", fontsize=10, weight="700", color=BG)

    summary_note = f"Profile Overview: {public_repos} Public Repos  •  {private_repos} Private Repos  •  {active_repos} Active Projects"
    ax_comp.text(0.0, 1.15, summary_note, ha="left", va="bottom",
                 fontsize=11, weight="600", color=TEXT_MUTED, transform=ax_comp.transAxes)

    for ax in [ax_growth]:
        ax.set_facecolor(PANEL)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(BORDER)
        ax.spines["bottom"].set_color(BORDER)
        ax.tick_params(colors=TEXT)

    fig.suptitle("GitHub Analytics", fontsize=32, weight="bold",
                 color=TEXT, y=0.98, fontfamily="sans-serif")

    fmt = Path(output_path).suffix.lstrip(".") or "svg"
    plt.savefig(output_path, format=fmt, facecolor=fig.get_facecolor(),
                bbox_inches="tight", pad_inches=0.3)
    plt.close()

    if fmt == "svg":
        add_clickable_links(output_path, top_repos)

    logger.info(f"Dashboard saved to {output_path} (theme={theme})")


def add_clickable_links(svg_path: str, top_repos: pd.DataFrame):
    """Add clickable hyperlinks to repository names in the SVG"""
    if "url" not in top_repos.columns:
        logger.warning("URL column not found, skipping clickable links")
        return

    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    for _, row in top_repos.iterrows():
        repo_name = row["name"]
        repo_url = row["url"]

        pattern = f"(<text[^>]*>)({re.escape(repo_name)})(</text>)"
        replacement = f'<a xlink:href="{repo_url}" target="_blank">\\1\\2\\3</a>'
        svg_content = re.sub(pattern, replacement, svg_content, count=1)

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    logger.info(f"Added clickable links to {len(top_repos)} repositories")