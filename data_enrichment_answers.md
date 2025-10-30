# Property Data Enrichment Strategy

## 5. Classification Pipeline for Construction Class
1. **Ingestion & Context Assembly**  
   - Use DocAutomate's `DocumentIngester` to pull broker uploads, permits, listings, and imagery into normalized text/image artifacts.  
   - Trigger an orchestration workflow (`universal-document.yaml`) that tags each artifact with building metadata (jurisdiction, year built, occupancy).
2. **Feature Extraction**  
   - **Imaging**: feed street/satellite/interior frames through a Vision Transformer (ViT-B/16) fine-tuned with DocAutomate's agent delegation for labeling; export embeddings plus saliency masks for structural cues (roof type, number of stories).  
   - **Textual/Tabular**: run PDF/txt inputs through a retrieval-augmented encoder (e.g., Llama-3.1-70B instruct) backed by a jurisdiction-specific knowledge base; convert tax tables and drawings via `spreadsheet_to_markdown` adapter for uniform schema.
3. **Multimodal Fusion**  
   - Concatenate vision embeddings with textual/document embeddings using a gated cross-attention fusion layer (similar to Flamingo).  
   - Add engineered features (construction year, occupancy class, code cycle) from the SQLite-backed metadata to form the final feature vector.
4. **Classification Head**  
   - Train an XGBoost classifier on fused embeddings to predict ISO construction class; include calibration (Platt scaling) so downstream catastrophe models receive well-calibrated probabilities.  
   - Deploy through DocAutomate's workflow engine with multi-model consensus (`claude_consensus`) for human-in-the-loop validation.
5. **Evaluation & Monitoring**  
   - Hold out recent buildings per jurisdiction; track F1 and calibration error.  
   - Use the built-in metrics collector (`collect_health_metrics`) to surface drift, triggering remediation workflows when confidence drops below a threshold.

Alternative considered: an end-to-end multimodal transformer (e.g., PaLI-3). Rejected initially because fine-tuning on limited labeled engineering data risks catastrophic forgetting and is harder to audit; the hybrid pipeline keeps interpretability via separate modality experts and DocAutomate's explainable workflows.

## 6. Structural Engineering Context Preparation & Architecture
- **Knowledge Consolidation**: ingest historical code documents, engineering interviews, and labeled imagery via a dedicated `context_ingestion` workflow. Store semantic vectors in a vector index (FAISS) keyed by jurisdiction, code version, and hazard type.  
- **Normalization**: map disparate code references to a canonical ontology (roof framing, lateral system, material). Use DocAutomate's YAML DSL to encode transformations and validation rules, ensuring each record captures applicability dates and exceptions.  
- **Label Harmonization**: align manual labels with catastrophe model requirements (e.g., RMS, AIR) by enforcing controlled vocabularies in the workflow outputs.  
- **Model Architecture**: adopt a retrieval-augmented multimodal transformer—text encoder (Llama-3) with cross-attention to ViT features; structural context retrieved per jurisdiction is added as prompts. The classifier head predicts both primary class and supporting attributes (roof pitch, load path).  
- **Continuous Updating**: schedule periodic DocAutomate workflows to refresh scraped data and retrain embeddings, logging deltas in `storage/database.py` for auditability.

## 7. Data Needed to Improve Accuracy
- Expanded labeled imagery (street, aerial, interior) with annotations for structural elements and degradation states.  
- Jurisdiction-specific permit datasets including code cycle and appeals outcomes.  
- Ground-truth post-event assessment reports to capture edge cases (retrofits, mixed construction).  
- Sensor-derived features (if available) such as LiDAR or thermal images for roof and façade composition.  
- Broker feedback loop captured via DocAutomate's remediation endpoints to collect corrected classifications and reasons.

## 8. Team Implementation Approach
- **Sprint Structure**: run two-week iterations where DocAutomate workflows define the deliverables; each sprint validates one jurisdiction or property type.  
- **Division of Labor**: I own pipeline architecture and workflow orchestration; the supporting AI engineer builds data loaders, labeling tools, and evaluation scripts; domain experts curate code context and validate outputs.  
- **Collaboration Rituals**: daily standups, mid-sprint model review using DocAutomate's dashboard, and end-of-sprint consensus review with engineers.  
- **Quality Gates**: enforce multi-model consensus thresholds before promoting a classifier; require documentation updates (`product/decisions.md`) for each architectural change.  
- **Knowledge Sharing**: maintain prompt libraries and label taxonomies in the DSL repo so new jurisdictions reuse templates; pair program on complex ingestion tasks to ensure redundancy.
