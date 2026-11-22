# Input Contract

# 1. Persona

The persona input defines the population participating in a simulation. Users can provide this data through either of the following options.

## 1.1. Persona Input Options

| Criteria | Option A: Upload File | Option B: Select Table |
|---|---|---|
| **Definition** | Client uploads a file containing persona data. The system processes the file and uses its records to create personas. | Client connects their database, selects a table containing persona data, and chooses which records to use for simulation. |
| **Accessibility** | ✓ Anyone with a supported data file can use the system. | ✗ Requires access to the client's database and permission to retrieve its data. |
| **Ease of Use** | ✓ The system can be hosted entirely on our infrastructure. The client only needs to upload a file. | ✗ Requires database connectivity and potentially deployment within the client's environment. |
| **Flexibility** | ✗ Simulating a different subset requires another file, or the client must simulate the entire population and filter the results afterward. | ✓ Records can be filtered using queries before being fed into the simulation. Different subsets can be selected without uploading new data. |
| **Data Preparation** | ✗ Clients may need to clean, restructure, or transform their files before uploading. | ✓ Existing tables can be inspected to understand their schema and identify relevant columns. |
| **Data Freshness** | ✗ Uploaded data represents a snapshot and can become outdated. | ✓ Can retrieve the latest available data whenever a simulation is initiated. |
| **Reusability** | ✗ Clients may need to upload the same or updated dataset repeatedly. | ✓ The same database connection and table can be reused across multiple simulations. |
| **Scalability** | ✗ Large datasets can make file transfers and processing cumbersome. | ✓ Avoids repeatedly transferring large datasets, although query performance and database capacity remain considerations. |
| **Data Ownership** | ✓ Clients explicitly choose what data to share by uploading a file. | ✗ Requires granting the system controlled access to the client's database. |
| **Security** | ✗ Uploaded data must be securely transferred, stored, and managed. | ✗ Requires secure database connections, authentication, and appropriate access controls. |
| **Complexity** | ✗ Files can have different formats and schemas, requiring additional backend processing, validation, and transformation. | ✗ Table schemas are already defined, but supporting different database systems introduces integration complexity. |

## 1.2. Verdict

**Preferred option: Select Table**

Select Table offers greater flexibility, reusability, data freshness, and scalability. These advantages become increasingly important when running multiple simulations against different population subsets.

The primary trade-off is the need for database connectivity and controlled access to the client's environment.

Upload File can remain an alternative for clients who cannot or do not want to provide database access.

---

# 2. Campaigns and Questions

A simulation consists of multiple campaigns, with each campaign containing its own set of questions.

## 2.1. Structure

- **Simulation:** Contains a name for tracking purposes, a persona population, and multiple campaigns.
- **Campaign:** Contains campaign details and a list of questions.
- **Question:** Contains the question name, type, instructions, and evaluation criteria.

Users can add as many campaigns and questions as they need within a simulation.

The same persona population is used across all campaigns within a simulation. To simulate a different population, the user creates a new simulation.

### Question Independence

Questions are evaluated independently.

- Question order does not matter.
- One question's response does not influence another question's response.
- Questions do not depend on previous answers.
- Each question is evaluated independently for every persona.

## 2.2. Question Configuration

Each question contains the following fields:

| Field | Description |
|---|---|
| **Question Name** | Identifies the question. |
| **Question Type** | Defines the expected response type: Noun, Choice, or Score. |
| **Instruction** | Explains what the persona should evaluate or answer. |
| **Criteria** | Defines the criteria for evaluating the response. |

All question types use the same configuration fields.

## 2.3. Question Reusability

Users can reuse questions through three operations:

- **Create New:** Create a question from scratch.
- **Import:** Reuse a saved question.
- **Copy:** Duplicate an existing question with all its fields prefilled. The user can modify any field before adding it.

Users can also save questions to a reusable question library. Saved questions can be imported into campaigns across different simulations.

## 2.4. Structure

A simulation contains a list of `campaigns` dictionaries. Each campaign contains its own `questions` dictionaries.

Each question is represented as an independent object within its campaign.

## 2.5. Example Skeleton

```json
[
   {
     "campaign_name": "",
     "campaign_details": "",
     "questions": [
       {
         "question_name": "",
         "question_type": "",
         "instruction": "",
         "criteria": ""
       }
     ]
  }
]
```