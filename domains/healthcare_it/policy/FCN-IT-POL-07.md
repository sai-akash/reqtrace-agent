# FCN-IT-POL-07: IT Change Policy

**Fictional document.** Fictional Clinic Network (FCN) is an invented organisation, and this policy was written for testing only. It isn't guidance for any real system.

**Tier definitions:** Tier 1 systems directly support patient care and must be restored quickly if they fail. Tier 2 systems are all other production systems.

**Scope:** Every rule applies to production changes, subject to the applicability stated in that rule. Each change request must contain the information needed to show that a rule is met.

## CHG-1 Test evidence

Applies to all production changes. The change request must record a completed test in a non-production environment, including the test date and outcome.

## CHG-2 Rollback plan

Applies to all production changes. The change request must include a rollback plan and an estimated rollback time. For Tier 1 systems, the estimated rollback time must not exceed 60 minutes.

## CHG-3 Maintenance window

Applies to Tier 1 systems only. Non-emergency changes must be deployed on a Sunday between 01:00 and 05:00 local time.

## CHG-4 Approvals

Applies to Tier 1 systems only. The change request must record approval from both the system owner and the Change Advisory Board (CAB).

## DAT-1 Test data

Applies when a change is tested using data. Test data must be synthetic or de-identified. Identifiable patient data must not be used in non-production environments.

## SEC-1 Vendor remote access

Applies when a change involves vendor remote access. Access must use multi-factor authentication (MFA) and must be limited to no more than 72 hours.

## SEC-2 Encryption in transit

Applies when a change adds or modifies an interface that transfers data between systems. The interface must use TLS 1.2 or higher.

## BCK-1 Database backup

Applies when a change alters a database schema or stored data. The change request must record a verified backup, completed or scheduled no more than 24 hours before deployment.
