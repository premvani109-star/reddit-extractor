import streamlit as st
import praw
from datetime import datetime
import io

# NEW: minimal imports for media download
import re
import requests
import zipfile

# Page config
st.set_page_config(
    page_title="Reddit Comment Extractor",
    page_icon="🔍",
    layout="wide"
)

# Initialize Reddit API
@st.cache_resource
def init_reddit():
    return praw.Reddit(
        client_id="ZDfutY72Y3ZtKgpPcuYXOg",
        client_secret="l4mKAywCvzHRhMnK3m3WrIGRZErHiw",
        user_agent="Reddit Main Branches Extractor v1.0"
    )

# ---------- MEDIA HELPERS (added) ----------
def _clean_url(u: str) -> str:
    return re.sub(r"&amp;", "&", u or "")

def get_op_media_urls(submission):
    """
    Return {'images': [...], 'videos': [...]} from OP.
    Images include gallery, single image, or preview source.
    Videos include Reddit-hosted fallback MP4 when available, and preview mp4.
    External embeds are listed in 'videos' as URLs but may not be downloadable.
    """
    images, videos = [], []

    # 1) Gallery: images and possible mp4s in media_metadata
    if getattr(submission, "is_gallery", False):
        media = getattr(submission, "media_metadata", {}) or {}
        for _, meta in media.items():
            if not isinstance(meta, dict):
                continue
            s = meta.get("s", {})
            # Prefer original
            if isinstance(s, dict):
                # mp4 or gif in galleries
                if "mp4" in s:
                    videos.append(_clean_url(s["mp4"]))
                elif "gif" in s:
                    videos.append(_clean_url(s["gif"]))
                # image
                if "u" in s:
                    images.append(_clean_url(s["u"]))
            # If only previews exist
            p = meta.get("p", [])
            if p and isinstance(p, list):
                u = p[-1].get("u")
                if u:
                    images.append(_clean_url(u))

    # 2) Single image via post_hint or direct extension
    post_hint = getattr(submission, "post_hint", "")
    if post_hint == "image" or submission.url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        images.append(_clean_url(submission.url))

    # 3) Reddit-hosted video
    if getattr(submission, "is_video", False):
        try:
            rv = (submission.media or {}).get("reddit_video", {})
            if "fallback_url" in rv:
                videos.append(_clean_url(rv["fallback_url"]))
        except Exception:
            pass

    # 4) Preview media for image or video
    preview = getattr(submission, "preview", None)
    if isinstance(preview, dict):
        try:
            imgs = preview.get("images", [])
            if imgs:
                src = imgs[0].get("source", {})
                if "url" in src:
                    images.append(_clean_url(src["url"]))
            # sometimes reddit_video_preview exists here
            rvp = preview.get("reddit_video_preview", {})
            if isinstance(rvp, dict) and "fallback_url" in rvp:
                videos.append(_clean_url(rvp["fallback_url"]))
        except Exception:
            pass

    # 5) Crosspost parent fallbacks
    try:
        parent_list = getattr(submission, "crosspost_parent_list", None)
        if parent_list and isinstance(parent_list, list) and parent_list:
            pprev = parent_list[0].get("preview", {})
            if "images" in pprev and pprev["images"]:
                src = pprev["images"][0].get("source", {})
                if "url" in src:
                    images.append(_clean_url(src["url"]))
            prv = parent_list[0].get("media", {}).get("reddit_video", {})
            if "fallback_url" in prv:
                videos.append(_clean_url(prv["fallback_url"]))
    except Exception:
        pass

    # Dedup while preserving order
    def _dedup(seq):
        seen = set()
        out = []
        for u in seq:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    return {
        "images": _dedup(images),
        "videos": _dedup(videos),
    }

def make_media_zip(media_dict, base_name="reddit_media"):
    """
    Download images and Reddit-hosted videos (fallback mp4) into a ZIP.
    Returns (BytesIO, filename) or (None, None) if nothing saved.
    """
    imgs = media_dict.get("images", [])
    vids = media_dict.get("videos", [])
    if not imgs and not vids:
        return None, None

    buf = io.BytesIO()
    saved_any = False
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Images
        for i, url in enumerate(imgs, start=1):
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                ext = ".jpg"
                for cand in [".png", ".jpeg", ".jpg", ".webp", ".gif"]:
                    if url.lower().split("?")[0].endswith(cand):
                        ext = cand
                        break
                zf.writestr(f"image_{i}{ext}", r.content)
                saved_any = True
            except Exception:
                continue

        # Videos: only download direct mp4 or gif-like URLs
        for j, url in enumerate(vids, start=1):
            try:
                clean = url.split("?")[0].lower()
                ext = ".mp4" if clean.endswith(".mp4") else ".gif" if clean.endswith(".gif") else ""
                # Only download if extension looks like a direct file
                if ext:
                    r = requests.get(url, timeout=30)
                    r.raise_for_status()
                    zf.writestr(f"video_{j}{ext}", r.content)
                    saved_any = True
                # Else skip streaming manifests like .m3u8
            except Exception:
                continue

    if not saved_any:
        return None, None

    buf.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return buf, f"{base_name}_{timestamp}.zip"
# -------------------------------------------

def extract_main_branches(reddit_url, num_replies=10):
    """Extract main comment branches with full text"""
    
    reddit = init_reddit()
    
    try:
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("🔍 Getting Reddit post...")
        progress_bar.progress(20)
        submission = reddit.submission(url=reddit_url)
        
        status_text.text("📊 Loading all comments...")
        progress_bar.progress(40)
        submission.comments.replace_more(limit=None)
        
        status_text.text("🌳 Processing main branches...")
        progress_bar.progress(60)
        
        # Generate content
        content = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ---------- OP BODY + MEDIA (added) ----------
        op_body = (submission.selftext or "").strip()
        if not op_body:
            parent_list = getattr(submission, "crosspost_parent_list", None)
            if parent_list and isinstance(parent_list, list) and parent_list:
                parent_text = (parent_list[0].get("selftext") or "").strip()
                if parent_text:
                    op_body = parent_text
        if not op_body:
            op_body = "(no body text)"

        media = get_op_media_urls(submission)
        # --------------------------------------------

        # Header
        content.append(f"POST: {submission.title}")
        content.append(f"BODY: {op_body}")
        # NEW: list media URLs
        if media["images"] or media["videos"]:
            content.append("MEDIA:")
            for i, u in enumerate(media["images"], start=1):
                content.append(f"[image {i}] {u}")
            for j, u in enumerate(media["videos"], start=1):
                content.append(f"[video {j}] {u}")
        content.append(f"SUBREDDIT: r/{submission.subreddit}")
        content.append(f"AUTHOR: u/{submission.author}")
        content.append(f"URL: {reddit_url}")
        content.append(f"SCORE: {submission.score} upvotes")
        content.append(f"TOTAL COMMENTS: {len(submission.comments.list())}")
        content.append("="*100)
        content.append("MAIN COMMENT BRANCHES - FULL TEXT")
        content.append("="*100)
        content.append("")
        
        # Process comments
        branch_count = 0
        total_comments = len(submission.comments)
        
        for idx, top_comment in enumerate(submission.comments):
            if hasattr(top_comment, 'body') and top_comment.body != '[deleted]':
                branch_count += 1
                
                author = str(top_comment.author) if top_comment.author else "[deleted]"
                score = top_comment.score
                reply_count = len(list(top_comment.replies.list())) if top_comment.replies else 0
                
                # Main comment
                content.append(f"🌳 BRANCH #{branch_count}")
                content.append(f"👤 Author: u/{author}")
                content.append(f"⬆️  Score: {score} points")
                content.append(f"💬 Replies: {reply_count}")
                content.append("─" * 80)
                content.append("MAIN COMMENT:")
                content.append(f"{top_comment.body}")
                content.append("─" * 80)
                content.append("")
                
                # Top replies
                if top_comment.replies and reply_count > 0:
                    content.append(f"📝 TOP {min(num_replies, reply_count)} REPLIES:")
                    content.append("▼" * 80)
                    
                    for i, reply in enumerate(top_comment.replies):
                        if i >= num_replies:
                            remaining = reply_count - num_replies
                            if remaining > 0:
                                content.append(f"\n... and {remaining} more replies ...")
                            break
                            
                        if hasattr(reply, 'body') and reply.body != '[deleted]':
                            reply_author = str(reply.author) if reply.author else "[deleted]"
                            reply_score = reply.score
                            
                            content.append(f"\n🔹 REPLY #{i+1} by u/{reply_author} ({reply_score} pts):")
                            content.append(f"{reply.body}")
                            content.append("┈" * 60)
                    
                    content.append("▲" * 80)
                
                content.append("\n" + "=" * 100)
                content.append("")
            
            # Update progress
            progress = 60 + (idx / total_comments) * 35
            progress_bar.progress(min(int(progress), 95))
        
        # Footer
        content.append(f"📊 SUMMARY:")
        content.append(f"• Total main branches: {branch_count}")
        content.append(f"• Total comments: {len(submission.comments.list())}")
        content.append(f"• Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        progress_bar.progress(100)
        status_text.text("✅ Complete!")
        
        filename = f"reddit_main_branches_{timestamp}.txt"

        # NEW: build ZIP if any media present and stash for download button
        zip_buf, zip_name = make_media_zip(media, base_name="reddit_media")
        st.session_state["__media_zip_buf"] = zip_buf
        st.session_state["__media_zip_name"] = zip_name

        return "\n".join(content), filename, branch_count
        
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return None, None, 0

# Main UI
st.title("🔍 Reddit Comment Extractor")
st.markdown("Extract main comment branches from any Reddit post")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    num_replies = st.slider("Replies per branch", 1, 20, 10)
    st.markdown("---")
    st.markdown("### 📖 How to use:")
    st.markdown("1. Paste a Reddit post URL")
    st.markdown("2. Click Extract")
    st.markdown("3. Download the results")

# Main interface
col1, col2 = st.columns([3, 1])

with col1:
    reddit_url = st.text_input(
        "Reddit Post URL",
        placeholder="https://www.reddit.com/r/subreddit/comments/post_id/title/",
        help="Paste the full URL of any Reddit post"
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)  # Spacing
    extract_button = st.button("🚀 Extract", type="primary")

# Results section
if extract_button and reddit_url:
    if not reddit_url.startswith("https://www.reddit.com/"):
        st.error("Please enter a valid Reddit URL")
    else:
        with st.spinner("Processing..."):
            content, filename, branch_count = extract_main_branches(reddit_url, num_replies)
            
            if content:
                st.success(f"✅ Extracted {branch_count} main branches!")
                
                # Download button - text
                st.download_button(
                    label="📄 Download Results",
                    data=content,
                    file_name=filename,
                    mime="text/plain"
                )

                # NEW: media ZIP button
                zip_buf = st.session_state.get("__media_zip_buf")
                zip_name = st.session_state.get("__media_zip_name")
                if zip_buf and zip_name:
                    st.download_button(
                        label="📦 Download OP Media (ZIP)",
                        data=zip_buf,
                        file_name=zip_name,
                        mime="application/zip"
                    )
                
                # Preview
                with st.expander("👁️ Preview Results", expanded=True):
                    st.text_area(
                        "Content Preview",
                        content[:2000] + "\n\n... (truncated for preview)" if len(content) > 2000 else content,
                        height=300
                    )

# Footer
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit")
