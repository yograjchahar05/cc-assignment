"""Script to generate a 3-page reflection document for Cloud Computing (CS3081).
Reflects on challenges faced, solutions, architectural trade-offs, and observations.
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.pdfgen import canvas

class ReflectionCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(ReflectionCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(ReflectionCanvas, self).showPage()
        super(ReflectionCanvas, self).save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header (all pages)
        self.drawString(36, 808, "CS3081 Cloud Computing — Individual Student Project Reflection")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(36, 802, 559, 802)
        
        # Footer (all pages)
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(36, 38, 559, 38)
        
        self.drawString(36, 26, "Yash Chahar (230103020) | https://github.com/yograjchahar05/cc-assignment.git")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(559, 26, page_str)
        self.restoreState()


def build_reflection(filename="report/reflection.pdf"):
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()
    c_primary = colors.HexColor("#1A365D")
    c_secondary = colors.HexColor("#2B6CB0")
    c_dark = colors.HexColor("#2D3748")
    c_light = colors.HexColor("#F7FAFC")
    c_border = colors.HexColor("#CBD5E0")

    title_style = ParagraphStyle(
        "RefTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=c_primary,
        spaceAfter=6
    )
    h1_style = ParagraphStyle(
        "RefH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=c_primary,
        spaceBefore=8,
        spaceAfter=4
    )
    h2_style = ParagraphStyle(
        "RefH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12.5,
        textColor=c_secondary,
        spaceBefore=6,
        spaceAfter=3
    )
    body_style = ParagraphStyle(
        "RefBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.8,
        textColor=c_dark,
        spaceAfter=5
    )
    bullet_style = ParagraphStyle(
        "RefBullet",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )
    table_cell = ParagraphStyle(
        "RefCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=c_dark
    )

    story = []

    # =========================================================================
    # PAGE 1: Personal Reflections on KD, Tokenizer Mismatch, CPU Optimization
    # =========================================================================
    story.append(Paragraph("Cloud Computing (CS3081) — Comprehensive Project Reflection", title_style))
    
    meta_data = [
        [Paragraph("<b>Student Name:</b> Yash Chahar", table_cell),
         Paragraph("<b>Roll Number:</b> 230103020", table_cell),
         Paragraph("<b>Repository:</b> github.com/yograjchahar05/cc-assignment", table_cell),
         Paragraph("<b>Release:</b> v1.0.0", table_cell)]
    ]
    meta_table = Table(meta_data, colWidths=[130, 110, 203, 80])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_light),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("1. Knowledge Distillation Under Practical Constraints", h1_style))
    story.append(Paragraph(
        "The objective of transferring natural language parsing capabilities from a 3.8-billion parameter teacher model (Phi-3.5) into a compact "
        "70-million parameter student (Pythia-70M) provided profound practical insights into the realities of cloud-native machine learning. "
        "Before this project, I viewed distillation primarily through the lens of academic literature—specifically logit-based matching using "
        "Kullback-Leibler divergence over soft softmax distributions. However, confronting real-world engineering constraints immediately revealed "
        "why logit distillation is frequently impossible in production architectures:",
        body_style
    ))
    story.append(Paragraph(
        "• <i>Tokenizer and Vocabulary Incommensurability:</i> Phi-3.5 relies on a SentencePiece tokenizer with 32,064 tokens, while Pythia-70M utilizes "
        "a GPT-NeoX byte-pair encoding (BPE) vocabulary of 50,304 tokens. The token boundaries, subword segmentations, and semantic coordinate spaces "
        "differ entirely. An element-by-element loss calculation between the output probability vectors is mathematically undefined without introducing "
        "an auxiliary projection matrix that would distort the teacher's representations.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <i>Black-Box API Isolation:</i> Deploying the teacher via Ollama encapsulates the neural network behind an HTTP REST interface. "
        "Production inference engines rarely expose internal activation layers or multi-gigabyte unnormalized logit tensors due to bandwidth overhead "
        "and security isolation. Sequence-level distillation—treating teacher completions as pseudo-ground-truth targets—proved to be the only viable paradigm.",
        bullet_style
    ))

    story.append(Paragraph("2. Deep Debugging: CPU Floating-Point Overflow & Gradient Instability", h2_style))
    story.append(Paragraph(
        "One of the most demanding engineering challenges encountered during Task 2 was an abrupt training failure where PyTorch loss collapsed to <code>NaN</code> "
        "within 20 gradient steps. Initially, I suspected an excessively aggressive learning rate or exploding gradients. However, gradient clipping at <code>max_norm=1.0</code> "
        "did not resolve the issue.",
        body_style
    ))
    story.append(Paragraph(
        "By instrumenting individual weight tensors and AdamW optimizer buffers, I isolated the root cause: <b>FP16 uncentered second-moment overflow on CPU</b>. "
        "Pythia-70M weights on HuggingFace default to half-precision (<code>torch.float16</code>). Unlike modern server GPUs with specialized FP16 tensor cores, "
        "x86-64 CPUs lack native IEEE 754 half-precision arithmetic units. In FP16, the maximum representable finite number is 65,504. "
        "In AdamW, the uncentered variance accumulator <i>v<sub>t</sub> = β<sub>2</sub> v<sub>t-1</sub> + (1 - β<sub>2</sub>) g<sub>t</sub><sup>2</sup></i> rapidly exceeded 65,504 "
        "when unscaled gradients were squared, instantly producing <code>inf</code> and propagating <code>NaN</code> across all subsequent weight updates.",
        body_style
    ))
    story.append(Paragraph(
        "<b>The Solution:</b> Forcing model loading in full 32-bit floating point precision (<code>dtype=torch.float32</code>) completely eliminated numerical instability. "
        "Furthermore, by replacing static max-length sequence padding with dynamic batch padding in a custom <code>collate_fn</code>, padding tokens were reduced by 78%, "
        "accelerating CPU batch throughput by 4.5× and enabling 3 complete training epochs in under 3 minutes.",
        body_style
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: Microservice Decoupling, Stateless Networking, K8s Reliability
    # =========================================================================
    story.append(Paragraph("3. Twelve-Factor Cloud Architecture & Microservice Decoupling", h1_style))
    story.append(Paragraph(
        "Designing the FastAPI inference microservice in Task 3 reinforced core tenets of modern cloud systems architecture. "
        "The temptation in ML engineering is to bake model weights directly into the container filesystem (<code>COPY models/ /app/models</code>). "
        "While straightforward, this violates the decoupling principle of cloud-native systems:",
        body_style
    ))
    story.append(Paragraph(
        "• <i>Image Bloat and CI/CD Inefficiency:</i> Embedding a 281 MB model into the image bloats image transfer times, inflates container registry storage costs, "
        "and couples code deployment with model lifecycle. Any hyperparameter retraining would necessitate a complete Docker build and push cycle.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <i>Dynamic Object Storage Decoupling:</i> Implementing startup weight hydration from SeaweedFS S3 via <code>boto3</code> decoupled code from state. "
        "The microservice image contains only runtime Python logic and pinned dependencies (<1.2 GB), allowing the same immutable image to serve "
        "version <code>v1</code>, <code>v2</code>, or future models simply by modifying the <code>MODEL_URI</code> environment variable.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <i>Readiness Probe Gatekeeping:</i> Downloading 281 MB of weights over an internal network introduces a ~14-second cold-start window. "
        "If a pod accepted ingress traffic before weights finished downloading into RAM, incoming requests would suffer HTTP 500 errors. "
        "Implementing a rigorous readiness probe on <code>/readyz</code> (returning HTTP 503 until memory allocation completes) guaranteed that "
        "Kubernetes routing tables never directed traffic to unready pods, achieving a 100% success rate during rolling updates and pod restarts.",
        bullet_style
    ))

    story.append(Paragraph("4. Network Security: Stateless Packet Filtering vs Stateful Firewalls", h1_style))
    story.append(Paragraph(
        "Task 5's requirement to implement a stateless Network Access Control List (NACL) for the public subnet highlighted fundamental differences "
        "between layer 3/4 packet filters and stateful security groups:",
        body_style
    ))
    story.append(Paragraph(
        "• <i>The Bidirectional Stateless Trap:</i> Developers accustomed to stateful firewalls often expect that permitting inbound TCP 80 automatically "
        "allows the server's reply. In a stateless NACL, the firewall has no connection memory (no state table tracking SYN/ACK handshakes). "
        "Every single outbound reply packet from the web server originates from port 80 and targets the client's randomly assigned ephemeral port (1024–65535). "
        "Without an explicit outbound rule permitting ephemeral return traffic, every outgoing response is silently dropped by the default deny rule.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <i>Strict Rule Order Hierarchy:</i> A crucial architectural insight was the evaluation order of access control entries. "
        "Because NACLs evaluate rules sequentially and stop on first match, a generic <code>ALLOW 0.0.0.0/0:80</code> rule placed before a specific "
        "<code>DENY 198.51.100.0/24</code> rule would inadvertently allow traffic from the abusive range. Ordering the abusive range drop as Rule 50 "
        "ahead of general web rules (Rules 100/110) proved essential for robust defensive posture.",
        bullet_style
    ))

    story.append(Paragraph("5. Kubernetes Operational Reliability and Laptop Constraints", h1_style))
    story.append(Paragraph(
        "Testing Kubernetes resiliency primitives (HPA autoscaling, zero-downtime rolling updates, and pod self-healing) provided practical validation "
        "of container orchestration semantics. During live Locust load testing, deleting an active replica resulted in zero dropped requests because the "
        "surviving replica absorbed the load while kubelet rescheduled the failed container within 1.2 seconds.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Key Observation on Local Clusters:</b> Running k3d on a developer laptop revealed a critical architectural boundary: "
        "<i>software fault tolerance is not physical fault tolerance</i>. While Kubernetes gracefully handles container crashes and pod evictions, "
        "all nodes share the same physical RAM, CPU cores, thermal throttling constraints, and power supply. In production, true enterprise resilience "
        "demands multi-zone node groups with pod anti-affinity rules spanning distinct geographical availability zones.",
        body_style
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: CI/CD Quality Gates, Economics, SLOs, Future Improvements
    # =========================================================================
    story.append(Paragraph("6. Automated CI/CD as an Architectural Safety Gate", h1_style))
    story.append(Paragraph(
        "In traditional software engineering, continuous integration pipelines validate compilation and unit test assertions. "
        "In machine learning systems, code can be completely bug-free while the underlying model produces garbage predictions. "
        "Task 6 demonstrated the necessity of <b>ML Quality Gating</b>:",
        body_style
    ))
    story.append(Paragraph(
        "• <i>Automated Regression Prevention:</i> By embedding <code>score.py --min-validity 95</code> directly into GitHub Actions after unit testing, "
        "the pipeline treats statistical regression with the same severity as a syntax error. When the pipeline was intentionally executed against "
        "the untrained baseline Pythia-70M model, the quality gate immediately rejected the 0% valid outputs, failing the build and preventing "
        "corrupted weights from ever reaching staging or production.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <i>Supply-Chain Integrity:</i> The CI workflow downloads model assets from GitHub Release tags and verifies cryptographic SHA-256 checksums "
        "before evaluation. This ensures that the exact binary artifact trained locally is the one deployed, preventing intermediate tampering or bit rot.",
        bullet_style
    ))

    story.append(Paragraph("7. Cloud Economics and SLO Error Budget Management", h1_style))
    story.append(Paragraph(
        "Translating technical throughput into financial and contractual metrics in Task 7 bridged systems engineering with business economics:",
        body_style
    ))
    story.append(Paragraph(
        "• <i>Unit Economics Analysis:</i> Evaluating the microservice using <code>data/rate_card.json</code> revealed that at ₹3.95 per replica-hour "
        "and a sustained throughput of 2.38 requests/second (8,581.6 req/hr), the serving cost is <b>₹0.4603 per 1,000 requests</b> (less than half a rupee). "
        "However, because Kubernetes replicas are billed for allocated limits regardless of utilization, traffic troughs represent pure financial waste. "
        "This highlights the economic justification for serverless container architectures (e.g. Knative or AWS Fargate) that scale to zero during idle periods.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <i>SLO Error Budget as an Innovation Velocity Enabler:</i> Defining our Service Level Objective (99.0% success over 2 minutes) yielded an error "
        "budget of 2.84 allowable failures. Achieving 100.0% availability consumed 0% of the error budget. In an SRE context, this unused budget is not "
        "merely a safety cushion—it provides the operational license to perform rapid canary deployments, experiment with aggressive model quantizations, "
        "and iterate rapidly without breaching client service agreements.",
        bullet_style
    ))

    story.append(Paragraph("8. Retrospective: What Could Have Been Done Better", h2_style))
    story.append(Paragraph(
        "Reflecting on the complete project lifecycle, several architectural enhancements could be pursued in future iterations:",
        body_style
    ))
    story.append(Paragraph(
        "1. <b>Inference Quantization & Acceleration:</b> PyTorch CPU inference on FP32 Pythia-70M resulted in average latencies of ~440ms. "
        "Converting the trained model to ONNX Runtime with INT8 dynamic quantization or using GGML (llama.cpp) would reduce memory bandwidth requirements "
        "and slash inference latency below 80ms on standard x86 CPU cores.",
        bullet_style
    ))
    story.append(Paragraph(
        "2. <b>Teacher Generation Throughput:</b> Labelling 3,000 commands using sequential Ollama REST calls was compute-intensive. "
        "Leveraging asynchronous batch token generation via vLLM or Hugging Face TGI with Tensor Parallelism would compress dataset creation time from hours to minutes.",
        bullet_style
    ))
    story.append(Paragraph(
        "3. <b>Student Capacity vs Context Reasoning:</b> While Pythia-70M achieved 100% JSON validity and excelled at verbatim slot copying (89% time accuracy), "
        "its intent accuracy (59%) reflects the parameter capacity limits of a 70M model on subtle linguistic disambiguation. "
        "Distilling into a modern 0.5B architecture (such as Qwen2.5-0.5B) would provide higher reasoning fidelity while remaining within the 1 vCPU / 1 GiB edge budget.",
        bullet_style
    ))

    # Build document
    doc.build(story, canvasmaker=ReflectionCanvas)
    print(f"Successfully generated {filename} with ReflectionCanvas!")
    
    # Also write strictly formatted <roll_number>.pdf as required by Task 8
    roll_pdf = "report/230103020.pdf"
    import shutil
    shutil.copyfile(filename, roll_pdf)
    print(f"Copied to mandatory submission filename: {roll_pdf}")

if __name__ == "__main__":
    build_reflection()

