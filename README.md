# Aegis: Self-Evolving Autonomous Agent Framework

Aegis is an autonomous agent architecture engineered for self-modification, dynamic skill acquisition, and deterministic execution. It moves beyond static prompt-chaining by treating skills, toolkits, and tasks as graph nodes that the agent can autonomously generate, register, and execute.

## Use Cases
* Currently, it can handle simple requests such as querying weather, or getting recipes for a dish. 
* "How is the weather in 61820?" and "How is the weather in San Francisco?" will result in the same skill DAG, guaranteeing a deterministic execution path to handle repeating queries.

## Core Architecture

Aegis executes tasks through a Directed Acyclic Graph (DAG). High-level objectives are systematically decomposed into modular sub-tasks, matched with active skills, and processed in a strict dependency order. 

* **Self-Evolution:** The agent bootstraps its own capabilities. Using base seed tasks (`build_skill`, `register_toolkit`), Aegis analyzes gaps in its current registry and generates executable modules to fulfill missing functional requirements when handling user requests. 
* **Sandboxed Execution:** Code execution and environment interactions are isolated within a subprocess runner, preventing contamination of the host file system.
* **Deterministic I/O:** Every skill and task is bounded by strict JSON schema validation, ensuring zero data hallucination between execution steps.

## Privacy & Human-In-The-Loop (HITL)

Aegis integrates a native privacy layer. Data streams are processed through an NLP-based scrubber to strip Personally Identifiable Information (PII) before LLM ingestion. A CLI-based approval workflow ensures that critical environment modifications and self-evolutionary steps require explicit human authorization before proceeding.

## Development Status

Aegis is currently under active development. Features that enable Aegis to create its own toolbox to access file system for handling user requests are currently being worked on. 

## Origin

The structural foundation for Aegis—specifically the separation of deterministic environment sensing, long-term semantic memory, and dynamic task formulation—originates from architectural concepts first developed in the [Environment Sensing CRS](https://github.com/skydiving94/environment_sensing_crs) project. Aegis represents the maturation of those initial context-aware memory and execution loops into a fully graph-based, self-modifying autonomous system.