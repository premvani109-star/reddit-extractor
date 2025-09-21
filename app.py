import streamlit as st
import praw
from datetime import datetime
import io

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

def extract_main_branches(reddit_url, num_replies=5):
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
        
        # Header
        content.append(f"POST: {submission.title}")
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
    num_replies = st.slider("Replies per branch", 1, 20, 5)
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
                
                # Download button
                st.download_button(
                    label="📄 Download Results",
                    data=content,
                    file_name=filename,
                    mime="text/plain"
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
