submission = reddit.submission(url=reddit_url)

# Ensure we only read publicly
reddit.read_only = True

# Build a robust body string for the OP
def get_op_body(sub):
    # Text/self post
    if getattr(sub, "is_self", False):
        if sub.selftext:
            return sub.selftext
        return "(self post with no body)"

    # Galleries
    if getattr(sub, "is_gallery", False):
        try:
            count = len(getattr(sub, "gallery_data", {}).get("items", []))
        except Exception:
            count = 0
        return f"(gallery post with {count} images) {sub.url}"

    # Media or link post
    if getattr(sub, "post_hint", None) in {"image", "rich:video", "hosted:video"}:
        return f"(media post) {sub.url}"

    # Fallback to the outbound link
    return f"(link post) {sub.url}"

op_body = get_op_body(submission)
