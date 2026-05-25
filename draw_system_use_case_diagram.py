from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, Rectangle


OUTPUT_DIR = Path(__file__).resolve().parent / "docs" / "diagrams"
FONT_FAMILY = ["Times New Roman", "SimSong", "Songti SC", "LiSong Pro", "Apple LiSung"]


def setup_style() -> None:
    plt.rcParams["font.family"] = FONT_FAMILY
    plt.rcParams["font.serif"] = FONT_FAMILY
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 180
    plt.rcParams["savefig.dpi"] = 320


def draw_actor(ax, x: float, y: float, label: str, color: str = "#2F4F6F") -> None:
    head = Circle((x, y + 0.42), 0.18, fill=False, linewidth=1.8, edgecolor=color)
    ax.add_patch(head)
    ax.plot([x, x], [y + 0.24, y - 0.25], color=color, linewidth=1.8)
    ax.plot([x - 0.38, x + 0.38], [y + 0.02, y + 0.02], color=color, linewidth=1.8)
    ax.plot([x, x - 0.35], [y - 0.25, y - 0.68], color=color, linewidth=1.8)
    ax.plot([x, x + 0.35], [y - 0.25, y - 0.68], color=color, linewidth=1.8)
    ax.text(x, y - 0.95, label, ha="center", va="top", fontsize=12, color=color)


def draw_external_actor(ax, x: float, y: float, label: str) -> None:
    draw_actor(ax, x, y, label, color="#4D5F4A")


def draw_use_case(
    ax,
    x: float,
    y: float,
    label: str,
    width: float = 2.15,
    height: float = 0.78,
    facecolor: str = "#F7FBFF",
    edgecolor: str = "#4E79A7",
) -> None:
    ellipse = Ellipse(
        (x, y),
        width,
        height,
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.45,
        zorder=2,
    )
    ax.add_patch(ellipse)
    ax.text(x, y, label, ha="center", va="center", fontsize=10.5, color="#1F2D3D", zorder=3)


def line(ax, start: tuple[float, float], end: tuple[float, float], color: str = "#536878") -> None:
    ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=1.25, zorder=1)


def relation(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    label: str,
    label_offset: tuple[float, float] = (0.0, 0.0),
) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.1,
        linestyle=(0, (5, 3)),
        color="#6C757D",
        zorder=1,
    )
    ax.add_patch(arrow)
    mx = (start[0] + end[0]) / 2 + label_offset[0]
    my = (start[1] + end[1]) / 2 + label_offset[1]
    ax.text(
        mx,
        my,
        label,
        ha="center",
        va="center",
        fontsize=9.2,
        color="#6C757D",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.5},
    )


def main() -> None:
    setup_style()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(15, 9.5))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 9.5)
    ax.axis("off")

    # System boundary
    boundary = Rectangle(
        (3.0, 0.75),
        9.2,
        8.0,
        facecolor="#FFFFFF",
        edgecolor="#2B3A42",
        linewidth=1.8,
    )
    ax.add_patch(boundary)
    ax.text(
        7.6,
        8.43,
        "企业法律咨询 RAG 系统",
        ha="center",
        va="center",
        fontsize=17,
        fontweight="bold",
        color="#1F2D3D",
    )

    # Human actors only
    draw_actor(ax, 1.25, 7.35, "法律咨询用户")
    draw_actor(ax, 13.75, 5.1, "人工客服", color="#8A5A20")
    draw_actor(ax, 1.25, 2.05, "系统管理员", color="#6D5A8D")

    # Function-level use cases
    cases = {
        "session": (4.85, 7.2, "新建/选择会话"),
        "ask": (7.55, 7.2, "提交法律咨询问题"),
        "qa": (10.25, 7.2, "智能法律问答"),
        "follow": (4.85, 5.7, "多轮追问"),
        "history": (7.55, 5.7, "历史对话管理"),
        "handoff": (10.25, 5.7, "人工客服转接"),
        "accept": (5.3, 3.8, "接入待处理会话"),
        "reply": (8.2, 3.8, "人工实时回复"),
        "kb": (5.3, 2.0, "法律知识库维护"),
        "model": (8.2, 2.0, "重排模型训练维护"),
    }

    for key, (x, y, label) in cases.items():
        if key in {"handoff", "accept", "reply"}:
            draw_use_case(ax, x, y, label, width=2.35, facecolor="#FFF9F0", edgecolor="#E49B45")
        elif key in {"kb", "model"}:
            draw_use_case(ax, x, y, label, width=2.45, facecolor="#F8F4FF", edgecolor="#8064A2")
        elif key in {"qa", "follow"}:
            draw_use_case(ax, x, y, label, width=2.35, facecolor="#F3FBF6", edgecolor="#59A14F")
        else:
            draw_use_case(ax, x, y, label, width=2.35)

    # User associations
    user_anchor = (1.68, 7.2)
    for target in ["session", "ask", "qa", "follow", "history", "handoff"]:
        x, y, _ = cases[target]
        line(ax, user_anchor, (x - 1.18, y))

    # Support associations
    support_anchor = (13.35, 5.0)
    for target in ["accept", "reply"]:
        x, y, _ = cases[target]
        line(ax, support_anchor, (x + 1.18, y), color="#8A5A20")

    # Admin associations
    admin_anchor = (1.68, 1.9)
    for target in ["kb", "model"]:
        x, y, _ = cases[target]
        line(ax, admin_anchor, (x - 1.22, y), color="#6D5A8D")

    # Minimal use-case relations
    relation(ax, (7.95, 7.2), (9.08, 7.2), "<<include>>", (0.0, 0.23))
    relation(ax, (5.68, 5.7), (9.08, 7.0), "<<include>>", (0.1, 0.2))
    relation(ax, (10.25, 5.98), (10.25, 6.82), "<<extend>>", (0.72, 0.0))
    relation(ax, (10.25, 5.42), (8.9, 4.1), "<<include>>", (0.45, 0.0))
    relation(ax, (5.98, 3.8), (7.02, 3.8), "<<include>>", (0.0, 0.22))

    # Legend
    legend_x, legend_y = 3.15, 9.1
    ax.plot([legend_x, legend_x + 0.55], [legend_y, legend_y], color="#536878", linewidth=1.25)
    ax.text(legend_x + 0.68, legend_y, "参与者关联", va="center", fontsize=9.5, color="#536878")
    arrow = FancyArrowPatch(
        (legend_x + 2.0, legend_y),
        (legend_x + 2.55, legend_y),
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.0,
        linestyle=(0, (5, 3)),
        color="#6C757D",
    )
    ax.add_patch(arrow)
    ax.text(legend_x + 2.7, legend_y, "包含/扩展关系", va="center", fontsize=9.5, color="#6C757D")

    fig.tight_layout()
    png_path = OUTPUT_DIR / "system_use_case_diagram.png"
    svg_path = OUTPUT_DIR / "system_use_case_diagram.svg"
    fig.savefig(png_path, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved use case diagram to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
