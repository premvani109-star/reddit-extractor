import os
import re
from datetime import datetime

import praw
import streamlit as st

# =========================
# Page config
# =========================
st.set_page_config(
    page_title="Reddit Comment Extractor",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Reddit Comment Extractor")
st.caption("Extract main comment branches with full text from any Reddit post URL.")

# =========================
# Secrets / Credentials
# =========================
def read_creds():
    """Read creds from Streamlit Secrets first, then env vars."""
    cid = csec = ua = None
    try:
        # Preferred: nested under [reddit] in secrets
        cid = st.secrets.get("reddit", {}).get("client_id")
        csec = st.secrets.get("reddit", {}).get("client_secret")
        ua = st.secrets.get("reddit", {}).get("user_agent")
    except Exception:
        pass

    # Fallback to flat secrets or environment
    cid = cid or st.secrets.get("client_id", os.getenv("REDDIT_CLIENT_ID"))
    csec = csec or st.secrets.get("client_secret", os.getenv("REDDIT_CLIENT_SECRET"))
    ua = ua or st.secrets.get("user_agent", os.getenv("REDDIT_USER_AGENT", "Reddit Main Branches Extractor v1.0"))

    return cid, csec, ua


@st.cache_resource(show_spinner=False)
def init_reddit():
    client_id, client_secret, user_agent = read_creds()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Reddit API credentials missing. Add them to Streamlit Secrets "
            "as either [reddit] section keys or flat keys: client_id, client_secret, user_agent."
        )
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )
    reddit.read_only = True
    return reddit


# =========================
# Helpers
# =========================
def get_op_body(submission):
    """Return a useful body string for the OP, covering self posts, media, galleries, and links."""
    try:
        # Self text post
        if getattr(submission, "is_self", False):
            if submission.selftext:
                return submission.selftext
            return "(self post with no body)"

        # Galleries
        if getattr(submission, "is_gallery", False):
            try:
                count = len(getattr(submission, "gallery_data", {}).get("items", []))
            except Exception:
                count = 0
            return f"(gallery post with {count} images) {submission.url}"

        # Common media hints
        post_hint = getattr(submission, "post_hint", None)
        if post_hint in {"image", "rich:video", "hosted:video"}:
            return f"(media post) {submission.url}"

        # Fallback to link
        return f"(link post) {submission.url}"
    except Exception:
        return "(unable to read OP body)"


def extract_main_branches(
    reddit_url: str,
    num_replies: int = 10,
    include_scores: bool = True,
    include_authors: bool = True,
    reddit: praw.Reddit | None = None,
):
    """Extract main comment branches with full text and return (content_text, filename, branch_count)."""
    if reddit is None:
        raise ValueError("Reddit client not initialized")

    # Progress UI
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        status_text.text("🔍 Getting Reddit post...")
        progress_bar.progress(10)
        submission = reddit.submission(url=reddit_url)

        # Build header info
        op_body = get_op_body(submission)

        status_text.text("📊 Loading all comments...")
        progress_bar.progress(30)
        # Expand all MoreComments for completeness
        submission.comments.replace_more(limit=None)

        status_text.text("📥 Caching comment tree...")
        progress_bar.progress(50)
        # Cache a flattened list for counting
        all_comments_flat = submission.comments.list()
        total_comment_count = len(all_comments_flat)

        # For progress, iterate top-level comments
        top_level = list(submission.comments)
        total_top = max(len(top_level), 1)

        status_text.text("🌳 Processing main branches...")
        progress_bar.progress(60)

        # Build content lines
        content_lines = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Header
        content_lines.append(f"POST: {submission.title}")
        content_lines.append(f"SUBREDDIT: r/{submission.subreddit}")
        content_lines.append(f"AUTHOR: u/{submission.author}" if include_authors else "AUTHOR: [hidden]")
        content_lines.append(f"URL: {submission.url}")
        if include_scores:
            content_lines.append(f"SCORE: {submission.score} upvotes")
        content_lines.append("")
        content_lines.append("BODY:")
        content_lines.append(op_body if op_body else "(no body)")
        content_lines.append("")
        content_lines.append(f"TOTAL COMMENTS: {total_comment_count}")
        content_lines.append("=" * 100)
        content_lines.append("MAIN COMMENT BRANCHES - FULL TEXT")
        content_lines.append("=" * 100)
        content_lines.append("")

        # Process branches
        branch_count = 0
        for i, top_comment in enumerate(top_level, start=1):
            # Update progress through top-level comments
            progress = 60 + int(35 * (i / total_top))
            progress_bar.progress(min(progress, 95))

            if not hasattr(top_comment, "body"):
                continue
            if top_comment.body == "[deleted]":
                continue

            branch_count += 1
            author = str(top_comment.author) if top_comment.author else "[deleted]"
            score = top_comment.score if hasattr(top_comment, "score") else 0

            # Count replies under this top comment
            try:
                reply_count = len(top_comment.replies.list()) if top_comment.replies else 0
            except Exception:
                reply_count = 0

            # Branch header
            content_lines.append(f"🌳 BRANCH #{branch_count}")
            if include_authors:
                content_lines.append(f"👤 Author: u/{author}")
            if include_scores:
                content_lines.append(f"⬆️  Score: {score} points")
            content_lines.append(f"💬 Replies: {reply_count}")
            content_lines.append("─" * 80)
            content_lines.append("MAIN COMMENT:")
            content_lines.append(f"{top_comment.body}")
            content_lines.append("─" * 80)
            content_lines.append("")

            # Top replies
            if top_comment.replies and reply_count > 0 and num_replies > 0:
                content_lines.append(f"📝 TOP {min(num_replies, reply_count)} REPLIES:")
                content_lines.append("▼" * 80)

                shown = 0
                for reply in top_comment.replies:
                    if shown >= num_replies:
                        remaining = reply_count - num_replies
                        if remaining > 0:
                            content_lines.append(f"\n... and {remaining} more replies ...")
                        break

                    if hasattr(reply, "body") and reply.body != "[deleted]":
                        reply_author = str(reply.author) if reply.author else "[deleted]"
                        reply_score = reply.score if hasattr(reply, "score") else 0
                        meta = []
                        if include_authors:
                            meta.append(f"u/{reply_author}")
                        if include_scores:
                            meta.append(f"{reply_score} pts")
                        meta_str = " ".join(m for m in meta if m)
                        meta_str = f" ({meta_str})" if meta_str else ""
                        content_lines.append(f"\n🔹 REPLY #{shown + 1}{meta_str}:")
                        content_lines.append(f"{reply.body}")
                        content_lines.append("┈" * 60)
                        shown += 1

                content_lines.append("▲" * 80)

            content_lines.append("\n" + "=" * 100)
            content_lines.append("")

        # Footer summary
        content_lines.append("📊 SUMMARY:")
        content_lines.append(f"• Total main branches: {branch_count}")
        content_lines.append(f"• Total comments: {total_comment_count}")
        content_lines.append(f"• Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        progress_bar.progress(100)
        status_text.text("✅ Complete!")

        filename = f"reddit_main_branches_{timestamp}.txt"
        return "\n".join(content_lines), filename, branch_count

    except Exception as e:
        status_text.text("❌ Error")
        progress_bar.progress(100)
        st.error(f"Error: {e}")
        return None, None, 0


# =========================
# Input Form (prevents reruns while typing)
# =========================
with st.form("controls", clear_on_submit=False):
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        reddit_url = st.text_input(
            "Reddit Post URL",
            value=st.session_state.get("reddit_url", ""),
            placeholder="https://www.reddit.com/r/AskReddit/comments/...",
            help="Paste a full Reddit post URL. Example: https://www.reddit.com/r/python/comments/abc123/post_title/",
            key="reddit_url_input",
        )
    with col2:
        num_replies = st.number_input(
            "Replies per branch",
            min_value=0,
            max_value=50,
            value=10,
            step=1,
            help="How many replies to show under each top-level comment.",
            key="num_replies_input",
        )
    with col3:
        include_scores = st.checkbox("Scores", value=True, key="scores_chk")
        include_authors = st.checkbox("Authors", value=True, key="authors_chk")

    run_btn = st.form_submit_button("Run Extraction", use_container_width=True, type="primary")

# =========================
# Validation and Run
# =========================
if run_btn:
    url = (reddit_url or "").strip()
    # Basic Reddit URL validation to catch copy-paste mistakes
    valid = re.match(r"^https?://(www\.)?reddit\.com/r/[^/]+/comments/[A-Za-z0-9]+/", url) or \
            re.match(r"^https?://(old\.)?reddit\.com/r/[^/]+/comments/[A-Za-z0-9]+/", url) or \
            re.match(r"^https?://(www\.)?redd\.it/[A-Za-z0-9]+/?", url)

    if not url or not valid:
        st.error("Please paste a valid Reddit post URL.")
        st.stop()

    # Persist inputs across reruns
    st.session_state["reddit_url"] = url
    st.session_state["num_replies"] = int(num_replies)
    st.session_state["include_scores"] = bool(include_scores)
    st.session_state["include_authors"] = bool(include_authors)

    try:
        reddit = init_reddit()
    except Exception as cred_err:
        with st.expander("Credentials error", expanded=True):
            st.error(str(cred_err))
            st.markdown(
                """
**How to set secrets**
1. In Streamlit Community Cloud: **App → Settings → Secrets**  
2. Add either:

