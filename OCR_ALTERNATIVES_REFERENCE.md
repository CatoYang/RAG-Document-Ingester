# OCR & Parsing Landscape Reference

This document serves as a historical reference for alternative Optical Character Recognition (OCR) models and parsing pipelines that were considered during the development of the RAG Document Ingester. It outlines the state-of-the-art tools as of mid-2026, their strengths, and why our current hybrid pipeline was chosen.

---

## 1. End-to-End Parsing Pipelines (CLI Tools)

These are massive, dedicated pipelines designed to take raw files (like PDFs) and convert them directly into structured Markdown or JSON.

### Marker (by Vik Paruchuri)
* **What it is:** A highly popular, open-source CLI pipeline specifically optimized for converting PDFs, EPUBs, and MOBI files to Markdown.
* **How it works:** It uses an ensemble of specialized deep-learning models (including Surya) to detect document layout, reading order, tables, and mathematical equations.
* **Pros:** Extremely accurate layout preservation and equation extraction.
* **Cons:** Very heavy. It requires downloading gigabytes of PyTorch weights and runs deep learning layout models on *every single page*, making it slow and resource-intensive for simple text documents.

### IBM Docling
* **What it is:** A modern, enterprise-grade Python library and CLI tool.
* **How it works:** Parses PDFs, Word, Excel, PPTX, and HTML into a unified Document schema, which can be exported as structured JSON or Markdown. It utilizes proprietary deep-learning models for table and layout recognition.
* **Pros:** Backed by IBM, supports a wide variety of office formats natively, and produces highly structured, predictable outputs.
* **Cons:** Like Marker, it relies heavily on PyTorch and large neural networks, making it significantly heavier than our current lightweight extraction routing.

---

## 2. Foundational OCR & Layout Engines

These are the underlying AI models that "read" the pixels and determine structure. They often power the pipelines mentioned above.

### Surya (by Vik Paruchuri)
* **What it is:** A CLI toolkit focused purely on line-level OCR, layout analysis (detecting where paragraphs and images are), and reading order.
* **How it works:** It does not output clean Markdown on its own. Instead, it provides the structural bounding boxes that pipelines like Marker use to assemble the final document.
* **Pros:** State-of-the-art layout detection for complex, multi-column documents.

### olmOCR (by AllenAI / AI2)
* **What it is:** An open-source toolkit and model family optimized for massive, batch-scale document conversion to Markdown.
* **How it works:** Rather than using traditional OCR logic, it leverages large Vision-Language Models (VLMs) like **Qwen2.5-VL** that have been heavily fine-tuned specifically for document extraction.
* **Pros:** Extremely high fidelity for archival and training data preparation. It excels at ignoring headers/footers and untangling messy handwriting.
* **Cons:** Designed primarily for large-scale data processing pipelines rather than lightweight local CLI execution.

### DeepSeek-OCR (by DeepSeek-AI)
* **What it is:** A vision-language architecture focused on efficiency rather than pure Markdown formatting.
* **How it works:** It reframes OCR as "Context Optical Compression." It uses a specialized vision encoder (like DeepEncoder V2) to compress visual information from a PDF page into a tiny, compact set of vision tokens.
* **Pros:** Reduces the number of tokens required to represent a document by 7–20x. This is incredibly powerful for feeding massive documents into LLMs without blowing up the context window memory.
* **Cons:** Less focused on generating human-readable Markdown output, and more focused on machine-readable token compression.

---

## 3. Our Current Architecture vs. The Alternatives

Our `RAG Document Ingester` is built as a **Lightweight Hybrid Pipeline**. It takes inspiration from Docling and olmOCR but is optimized specifically for speed, local control, and avoiding heavy PyTorch dependencies.

### Why our pipeline is uniquely suited for this vault:
1. **Intelligent Triage (Speed):** Tools like Marker run heavy AI layout models on every single page. Our `DocumentRouter` checks the text density of a PDF first. If it's a simple, text-heavy page, it parses it instantly using `PyMuPDF` (Tier 1) in milliseconds.
2. **Selective Heavy Lifting (Accuracy):** When the router detects a complex, image-heavy RPG page (or a standalone `.jpg`), it routes it to Ollama (Tier 3), utilizing the exact same VLM models (like Qwen2.5-VL or MiniCPM-V) that power cutting-edge engines like olmOCR.
3. **Universal Office Support:** Instead of reinventing parsing for Word and Excel, we offload Office formats to Microsoft's lightweight `MarkItDown` library, achieving Docling-level format support without the gigabytes of neural network weights.

### When to switch in the future:
* **Switch to Marker/Docling:** If you find that the pipeline is struggling to preserve highly complex, nested tables or multi-column layouts across hundreds of PDFs, and you don't mind sacrificing speed and disk space for accuracy.
* **Switch to DeepSeek-OCR:** If your downstream RAG LLM is constantly running out of context memory, and you need a way to compress the visual tokens of your documents rather than storing them as raw Markdown text.
