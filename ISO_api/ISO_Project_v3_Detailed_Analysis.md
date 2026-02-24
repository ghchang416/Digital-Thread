# ISO Project v3 API Code Analysis (Focused Version)

## 1. Scope of This Analysis

This document analyzes the uploaded `iso_project_code.zip` based
strictly on **v3 API only**.

-   Non-v3 routers imported in `main.py` are intentionally ignored.
-   The focus is on:
    -   Project XML upload
    -   CAM JSON parsing
    -   WorkingStep creation
    -   dt_cutting_tool_13399 generation
    -   Data Platform upload flow

------------------------------------------------------------------------

# 2. High-Level Architecture (v3 Only)

    src/
     ├── main.py
     ├── config.py
     ├── database.py
     │
     ├── apis/v3/
     │    ├── asset.py
     │    └── project.py
     │
     ├── services/
     │    ├── asset.py
     │    ├── file.py
     │    ├── v3_project.py
     │    └── __init__.py
     │
     ├── entities/
     │    ├── asset.py
     │    ├── file.py
     │    └── model_v31.py
     │
     ├── schemas/
     │    ├── asset.py
     │    ├── file.py
     │    └── project.py
     │
     └── utils/
          ├── v3_xml_parser.py
          ├── cam_common.py
          ├── cam_nx_adapter.py
          ├── cam_powermill_adapter.py
          ├── nc_spliter.py
          ├── file_modifier.py
          ├── xml_parser.py
          ├── asset_xml_parser.py
          ├── stock.py
          ├── exceptions.py
          └── env.py

------------------------------------------------------------------------

# 3. v3 API Endpoints

## 3.1 /api/v3/assets

Handles dt_asset lifecycle.

### Core Responsibilities

-   Upload dt_asset XML
-   Store metadata in MongoDB
-   Store file content in GridFS (if dt_file)
-   Delete / Update / Query assets
-   Generate dt_file from NC upload

### Main Service Layer

-   AssetService
-   FileService

------------------------------------------------------------------------

## 3.2 /api/v3/projects

Handles ISO project operations.

### Important Endpoints

  -----------------------------------------------------------------------
  Endpoint                              Purpose
  ------------------------------------- ---------------------------------
  POST /projects                        Upload dt_project

  GET /projects                         List projects

  POST /projects/add-ref                Attach asset reference

  PUT /projects/delete-ref              Remove reference

  POST /projects/cam-json               CAM → WorkingStep + Tool
                                        generation

  POST /projects/upload-platform        Upload project + related assets
                                        to Data Platform
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 4. CAM → ISO Flow (Core of the System)

The most important logic exists in:

    POST /api/v3/projects/cam-json

This endpoint performs:

1.  Find NC dt_file associated with project
2.  Extract tool sequence (T1, T2, T3...) from NC
3.  Parse CAM JSON (NX or PowerMill)
4.  Validate tool count vs operation count
5.  Generate dt_cutting_tool_13399 assets
6.  Generate WorkingStep XML nodes
7.  Inject tool references
8.  Validate against schema
9.  Save tools first
10. Update project XML with new WorkingSteps
11. Rollback tool creation on failure

------------------------------------------------------------------------

# 5. dt_cutting_tool_13399 Generation

Implemented mainly in:

-   utils/cam_common.py
-   utils/v3_xml_parser.py

### Key Logic

-   One 13399 tool per unique T-number
-   Tool values extracted from CAM mapping JSON
-   Fullpath reference injected into WorkingStep
-   Schema compliance enforced via helper functions

------------------------------------------------------------------------

# 6. Project Upload to Data Platform

Handled by:

    POST /api/v3/projects/upload-platform

Service:

    V3ProjectService.upload_project_and_related()

### Upload Flow

1.  Upload dt_project XML
2.  Collect referenced assets
3.  Upload assets by type:
    -   dt_file (with binary)
    -   dt_material
    -   dt_machine_tool
    -   dt_cutting_tool_13399
4.  Mark uploaded documents in DB

------------------------------------------------------------------------

# 7. Execution Integrity Check

### Observed Structural Issues

1.  services/**init**.py imports modules not present in zip
2.  main.py imports non-v3 routers (ignored for analysis)
3.  src.config import mismatch risk if file not aligned

To run v3 cleanly, services/**init**.py must match actual services.

------------------------------------------------------------------------

# 8. Do I Fully Understand the Code?

## Yes --- Architecturally and Logically

I understand:

-   The full CAM → WorkingStep → 13399 generation flow
-   Mongo + GridFS persistence model
-   Tool caching behavior
-   Schema validation + rollback strategy
-   Data Platform upload orchestration

## But Not 100% Runtime Context

I do NOT yet know:

-   Actual XML schema files used
-   Real CAM JSON examples used in production
-   External Data Platform API behavior
-   Production config (env, DB, credentials)

### Conclusion

Architecturally and logically: **I understand the system completely.**\
Environment-specific runtime behavior: **requires real deployment
context.**

------------------------------------------------------------------------

# 9. Summary

The v3 API implements a complete ISO-based Digital Thread pipeline:

    Project XML
       ↓
    NC Tool Sequence Extraction
       ↓
    CAM JSON Mapping
       ↓
    WorkingStep Generation
       ↓
    dt_cutting_tool_13399 Creation
       ↓
    Schema Validation
       ↓
    Mongo + GridFS Persistence
       ↓
    Data Platform Upload

This is not a simple CRUD API --- it is a structured ISO 14649
orchestration engine.
