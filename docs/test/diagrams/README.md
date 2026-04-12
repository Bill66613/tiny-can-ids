# PlantUML Diagrams Reference

This directory contains architecture and workflow diagrams for the integration testing framework. Each diagram is a standalone `.puml` file for easy reuse and maintenance.

## Diagram Index

### 1. [01-data-feeder-architecture.puml](01-data-feeder-architecture.puml)
**Purpose:** Class diagram showing the Data Feeder system structure  
**Shows:** DataFeeder, Scenario, ScenarioConfig classes and their relationships  
**Used in:** 01-data-feeder-design.md  
**Key elements:**
- DataFeeder class (central provisioning system)
- Scenario class (individual test data generators)
- ScenarioConfig (configuration parameters)
- ScenarioSize enum (tiny, small, medium, large)
- DatasetType enum (synthetic or real data)

---

### 2. [02-data-flow.puml](02-data-flow.puml)
**Purpose:** State diagram for data flow through the system  
**Shows:** How test data flows from DataFeeder initialization through pipeline execution  
**Used in:** 01-data-feeder-design.md  
**Key elements:**
- DataFeeder initialization
- Scenario generation and preprocessing
- Feature extraction
- Test data provisioning
- Pipeline execution and validation

---

### 3. [03-integration-pipeline-flow.puml](03-integration-pipeline-flow.puml)
**Purpose:** Comprehensive state diagram for integration test execution  
**Shows:** Full end-to-end test flow with data scenarios and validation steps  
**Used in:** 02-integration-pipeline-design.md (referenced in two sections)  
**Key elements:**
- DataFeeder setup
- 4 scenario branches (tiny/small/medium/large)
- Pipeline execution
- Output validation (C files, TFLite, metrics, compilation)
- Pass/Fail outcomes

---

### 4. [04-test-categories.puml](04-test-categories.puml)
**Purpose:** Component diagram showing test organization  
**Shows:** How unit, integration, and performance tests relate to each other  
**Used in:** 03-automation-framework.md  
**Key elements:**
- Unit tests (data, features, models, export modules)
- Integration tests (pipeline output validation)
- Performance tests (baseline and memory)
- Dependencies between test categories

---

### 5. [05-failure-response.puml](05-failure-response.puml)
**Purpose:** State machine for test failure handling  
**Shows:** Appropriate responses to different test failure scenarios  
**Used in:** 03-automation-framework.md  
**Key elements:**
- Unit test failure handling
- Integration test failure handling
- Report generation
- Notification workflow

---

## Reuse Patterns

### Cross-referenced Diagrams
- **03-integration-pipeline-flow.puml** is referenced in two sections of 02-integration-pipeline-design.md

### Consistent Styling
All diagrams follow the same color scheme:
- Input states: orange
- Process states: blue
- Output states: green
- Failure states: red
- Background: light gray

---

## Rendering Diagrams

To view or render these PlantUML diagrams:

### Online Viewers
- [PlantUML Editor](http://www.plantuml.com/plantuml/uml/)
- [Kroki.io](https://kroki.io/)
- GitHub (uses native PlantUML support)
- GitLab (native support)

### Local Rendering

Install PlantUML:
```bash
# macOS
brew install plantuml

# Ubuntu
apt-get install plantuml
```

Render individual diagrams:
```bash
plantuml docs/test/diagrams/01-data-feeder-architecture.puml -o ../rendered/
```

Render all diagrams:
```bash
for diagram in docs/test/diagrams/*.puml; do
    plantuml "$diagram" -o ../rendered/
done
```

---

## Maintenance Guidelines

When updating diagrams:
1. Edit the `.puml` file directly
2. Maintain style consistency with other diagrams
3. Update references in markdown files if diagram structure changes
4. Test rendering in your preview tool

---

## Extension Points

Diagrams for potential future additions:
- CI/CD workflow pipeline
- Pytest marker organization
- Performance baseline tracking
- Deployment architecture
