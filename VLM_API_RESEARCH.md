# Vision Language Model (VLM) API Research & Architecture Strategy

## 1. The Core Problem: Local-First Architecture vs. Cloud API Throttling
Our current extraction pipeline was originally designed for local Ollama models (e.g., `minicpm-v`). 
- **Local Models:** Zero request limits, but tiny memory windows (VRAM crashes if you send large/multiple images).
- **Cloud APIs:** Massive context windows (1+ million tokens), but **heavy throttling on Request Frequency (RPM/RPD)**.

By simply hot-swapping the Gemini API into our local-first architecture (firing 1 request *per image*), we instantly burned through the Free Tier quotas.

### Google Gemini Free-Tier Constraints (2026)
Google AI Studio offers access to their newest models, but strictly throttles them for free users:
- **`gemini-3.8-flash`**: 2 RPM / **20 Requests Per Day**
- **`gemini-3.6-flash`**: 2 RPM / **20 Requests Per Day**
- **`gemini-3.5-flash`**: 5 RPM / ~50 Requests Per Day

*Conclusion:* Extracting a 130-image D&D book one image at a time takes 130 requests, which mathematically cannot be completed on the current free tiers without batching.

---

## 2. Paid API Market Research (As of Sept 2026)

If you wish to bypass the Free Tier completely and avoid batching, here are the current market rates for the leading Vision Language Models.

*Note: In the VLM world, an image is typically tokenized at a flat rate. For example, Gemini charges exactly 258 tokens per image, while OpenAI scales based on resolution (average 200-1000 tokens per image).*

| Provider & Model | Input Price (Per 1M Tokens) | Output Price (Per 1M Tokens) | Context Window | Rate Limits (Tier 1 Paid) |
| :--- | :--- | :--- | :--- | :--- |
| **Google Gemini 3.8 Flash** | $0.75 | $3.75 | 2,000,000 | 1000+ RPM (Scales w/ spend) |
| **OpenAI GPT-4o** | $2.50 | $10.00 | 128,000 | 500 RPM / 300,000 TPM |
| **Anthropic Claude 3.5 Sonnet**| $3.00 | $15.00 | 200,000 | 50 RPM / 40,000 TPM |

### Cost Estimation for D&D Book Ingestion
Assuming a 300-page D&D book with **150 Images**:
- **Image Input Tokens:** ~40,000 tokens
- **Text Prompt Input:** ~10,000 tokens
- **OCR Output Generation:** ~20,000 tokens

**Total Cost per Book:**
- **Gemini 3.8 Flash:** ~$0.11 per book
- **GPT-4o:** ~$0.32 per book
- **Claude 3.5 Sonnet:** ~$0.45 per book

*Bonus:* All of these providers offer a **Batch API** (asynchronous processing where you submit a JSONL file and get results in 24 hours). Batch APIs offer a strict **50% discount** on all prices listed above.

---

## 3. Structural Solutions (Moving Forward)

Based on this research, we have two primary paths to fix the pipeline structurally:

### Option A: The "Batch Payload" Rewrite (Free Tier Friendly)
We rewrite the `HybridPdfExtractor` to gather all images in a PDF first, then send **1 single API request** to Gemini with all 130+ images packed inside its massive 1 Million Token context window.
- **Cost:** Free. Uses exactly 1 request out of your daily quota.
- **Challenge:** We must use Strict JSON Structured Outputs to force the model to map each description to its specific file name so we can inject them back into the Markdown accurately. There is a slight risk the model "skips" an image when processing 150 at once.

### Option B: Switch to Paid / Pay-As-You-Go API
You link a credit card to Google AI Studio or OpenAI to unlock Tier 1 paid status. We keep our current "One-By-One" extraction loop (which is highly reliable for mapping).
- **Cost:** ~$0.10 to $0.30 per book. 
- **Challenge:** Requires setting up a billing account. However, you completely bypass the 20 RPD limits and can process books at lightspeed.
