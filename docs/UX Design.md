# UX Design

## 1. Overview

The UX allows users to configure and run persona-based simulations by providing three primary inputs:

1. **Persona:** Defines the population participating in the simulation.
2. **Campaign:** Defines what the personas will evaluate.
3. **Questions:** Defines what we want to learn from the personas' responses.

A simulation can contain one persona set, multiple campaigns, and multiple questions per campaign.

---

## 2. Simulation Setup

The user starts by selecting **Let's Get Simulating**.

They are prompted to enter a simulation name and select a model.

- **Simulation Name:** Used to identify and track simulations. The name does not affect the simulation itself.
- **Model Name**: Model used to run simulation

---

## 3. Persona Selection

The user chooses how to provide persona data.

### Option A: Upload File

The user uploads a file containing persona data.

### Option B: Select Table

The user connects to their database and selects a table containing persona data.

The user can then select the relevant population using filters before feeding the records into the simulation.

**Selected Columns**

The user selects which columns the simulation should retrieve from the table.

The selection is stored as a dictionary:

```
{
  "id": "persona_id",
  "persona_column": "persona_summary",
  "other_columns": ["age", "region", "income"]
}
```

- `id`: Unique identifier for each persona.
- `persona_column`: Column containing the persona representation.
- `other_columns`: Additional attributes to retain for segmentation and analysis.

**Filters**

Filters are stored as a list of dictionaries. Each dictionary represents one filter.

```
[
  {
    "column": "age",
    "type": "slider",
    "values": [25, 45]
  },
  {
    "column": "region",
    "type": "multi_select",
    "values": ["West", "South"]
  }
]
```

Supported filter types:

| Filter type     | Operation | Values                       |
| --------------- | --------- | ---------------------------- |
| `single_select` | `=`       | One value                    |
| `multi_select`  | `IN`      | List of values               |
| `slider`        | `BETWEEN` | Minimum and maximum integers |

**Schema Retrieval**

When the user selects or enters a table name, the frontend retrieves its schema, including column names and data types.

The available filter types are determined by the selected column's datatype. For example:

| Column datatype | Available filter types                    |
| --------------- | ----------------------------------------- |
| INTEGER         | `single_select`, `multi_select`, `slider` |
| REAL            | `single_select`, `multi_select`           |
| TEXT            | `single_select`, `multi_select`           |
| BOOLEAN         | `single_select`, `multi_select`           |

The frontend only offers filter types supported by the selected column's datatype.

The selected persona population applies to all campaigns within that simulation. If the user wants to simulate a different population, they create a new simulation.

---

## 4. Campaigns and Questions

After selecting the persona population, the user proceeds to campaign configuration.

A simulation can contain multiple campaigns. Each campaign can have multiple questions.

### 4.1 Campaign Details

The user provides the campaign details.

Each campaign should also have a name to distinguish it from other campaigns.

### 4.2 Adding Questions

Under each campaign, the user can click **Add Question**.

For every new question, the user provides:

1. **Question Name:** Identifies the question.
2. **Question Type:** Selects the expected response type.
   - Noun
   - Choice
   - Score
3. **Instructions:** Explains what the persona should evaluate or answer.
4. **Criteria:** Defines the criteria for evaluating the response.

All question types use the same set of configuration fields.

### 4.3 Adding Multiple Campaigns

The user can add as many campaigns as needed within a simulation.

Each campaign has its own set of questions.

When adding questions to subsequent campaigns, the user has three options:

- **Create New:** Create a question from scratch.
- **Import:** Reuse an existing question from a saved question. (Will automatically mark is_saved to 1 and reuse ID)
- **Copy:** Duplicate an existing question, prefilled with its original configuration. The user can modify any field before adding it.

### 4.4 Saving Questions

Users can save questions to a reusable question library.

Saved questions can be imported into campaigns across different simulations.

This avoids repeatedly configuring the same questions for different experiments.

### Saving and Reusing Campaigns & Questions

- Users can choose to save campaigns and questions for future reuse.
- Saved campaigns and questions are persisted immediately by the frontend and become available for selection in subsequent experiments. frontend adds the question_id to the data structure for the backend to use
- Unsaved campaigns and questions are temporary and are persisted by the backend when an experiment is initiated.
- Both saved and unsaved records are associated with the relevant experiment when used.

---

## 5. Question Independence

Questions are evaluated independently.

- Question order does not matter.
- One question's response does not influence another question's response.
- Questions do not depend on previous answers.
- Each question is evaluated independently for every persona.

---

## 6. Overall Input Flow

The overall configuration follows this hierarchy:

Simulation

- Simulation Name
- Persona
  - Upload File OR Select Table
  - Select Population / Apply Filters
  - Select columns to be included in output to aid aggregations
- Campaigns
  - Campaign 1
    - Campaign Details
    - Questions
      - Question 1
      - Question 2
  - Campaign 2
    - Campaign Details
    - Questions
      - Question 1
      - Question 2

The user can add as many campaigns and questions as needed.

The persona population remains the same across all campaigns within a simulation.