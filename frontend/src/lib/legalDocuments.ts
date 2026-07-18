/**
 * legalDocuments.ts — the actual Xoltra Terms of Service and Privacy Notice
 * text, rendered directly in TermsConsentGate instead of an external link.
 *
 * POLICY_VERSION must match backend/auth.py's CURRENT_POLICY_VERSION exactly
 * — it's not read from here at runtime, it's just a reminder to update both
 * together whenever the "Effective date" on either document changes.
 */

export const POLICY_VERSION = '2026-07-13';
export const POLICY_EFFECTIVE_DATE = 'July 13, 2026';

export const TERMS_OF_SERVICE_TEXT = `XOLTRA | TERMS OF SERVICE
Effective date: July 13, 2026

1. Who We Are and What These Terms Cover

These Terms of Service (the "Terms") are an agreement between you and Xoltra, doing business as Xoltra ("Xoltra," "we," "us," or "our"). They govern your access to and use of the Xoltra software, websites, applications, APIs, workflows, AI features, simulation features, integrations, and related services (collectively, the "Service").

By creating an account, accessing the Service, uploading or submitting content, connecting a third-party account, approving an automation, or otherwise using the Service, you agree to these Terms. If you use the Service for an organization, you represent that you have authority to bind that organization; "you" and "your" include that organization.

If you do not agree to these Terms, do not use the Service. A separately signed agreement with us controls to the extent it conflicts with these Terms.

2. Eligibility and Account Responsibility

You must be at least 18 years old and legally capable of entering into this agreement. You may not use the Service if you are prohibited from doing so under applicable law or if we previously suspended or terminated your access.

You must provide accurate, complete, and current account information, protect your credentials and connected-account credentials, and promptly notify us at [SUPPORT EMAIL] of any suspected unauthorized use. You are responsible for activity undertaken through your account, including actions taken by people you authorize and automations you approve.

You may not share access in a manner that exceeds your subscription, defeats security controls, or permits an unauthorized person to use the Service.

3. The Service

Xoltra is an AI-assisted automation and productivity platform. Depending on the features available to you, it may help create workflow plans from natural-language instructions, provide role-based AI assistance, process text and supported documents, retain selected conversation-derived knowledge, visualise simulations, and connect with approved third-party tools or local resources.

We may add, change, suspend, or discontinue features, models, integrations, usage limits, or access tiers. We will not materially reduce a paid service during a prepaid term unless we provide reasonable notice or a substantially equivalent alternative, except where a change is necessary for security, legal compliance, or a third-party dependency.

The Service may be offered in preview, beta, trial, or experimental form. Those features may be incomplete, unreliable, changed without notice, or withdrawn, and are provided on an "as available" basis.

4. Your Content, Files, and Instructions

"Customer Content" means the prompts, goals, chat messages, uploaded files, workflow configurations, integration data, instructions, and other information you submit to, make available through, or cause the Service to access. You retain any rights you have in Customer Content.

You grant Xoltra a worldwide, non-exclusive, royalty-free right to host, reproduce, process, transmit, adapt, and display Customer Content solely as necessary to operate, secure, support, improve, and provide the Service, comply with law, and enforce these Terms. This permission includes processing Customer Content through our model, hosting, storage, security, analytics, and integration providers as described in our Privacy Notice.

You represent and warrant that you have all rights, permissions, consents, and lawful bases needed to submit Customer Content, instruct us to process it, connect each third-party account, and authorize the requested actions. Do not submit personal, confidential, regulated, export-controlled, or highly sensitive information unless the Service documentation and our written agreement expressly permit that use and you have completed any required safeguards.

You are solely responsible for Customer Content, your instructions, and all results of actions taken using your account. You must keep independent copies of important data. Xoltra is not a backup or records-retention service unless we expressly agree otherwise in writing.

5. AI Features and Output

The Service uses artificial intelligence and may route requests among different models or processing steps based on the nature of your request. AI-generated responses, plans, summaries, workflow suggestions, classifications, simulations, and other results are collectively "Output." Output may be inaccurate, incomplete, misleading, non-unique, or unsuitable for your purpose.

You must independently review and validate Output before relying on it, publishing it, executing it, or using it to make a decision. You are responsible for confirming facts, calculations, legal and regulatory requirements, safety, permissions, and suitability for your circumstances. Do not treat Output as medical, legal, financial, tax, employment, insurance, investment, mental-health, emergency, or other professional advice.

As between you and Xoltra, and to the extent permitted by law, you retain rights in your Customer Content and we assign to you any rights we may have in Output generated specifically for you. This assignment does not guarantee that Output is protectable, non-infringing, accurate, exclusive, or available for any particular use. Similar or identical Output may be generated for other users.

6. Persistent Knowledge and Context Features

If enabled or used, Xoltra may create and retain knowledge records from your goals, workflow plans, document-derived goals, saved sessions, summaries, preferences, recurring themes, or inferred patterns. These records may be stored locally or in the storage environment associated with your deployment and may be retrieved to provide context for future responses.

Before saving a conversation, uploading a document, or enabling a knowledge feature, make sure you are authorized to retain and process that information for this purpose. You are responsible for reviewing the accuracy of saved summaries and inferred patterns. Inferences may be incorrect and must not be treated as factual records about you or another person.

Your privacy choices, deletion requests, and rights concerning these features are governed by our Privacy Notice and applicable law. Where a deletion control is offered, it may not remove data that must be retained for security, legal, accounting, fraud-prevention, or backup-restoration purposes.

7. Third-Party Models, Services, and Integrations

The Service may use third-party AI, hosting, storage, analytics, or integration providers. In the current product architecture, requests and text-derived data may be transmitted to an external AI model provider, including Cohere, to generate responses, summaries, embeddings, or related results. Your use may also be subject to the terms, policies, and technical limits of those providers.

If you connect an external account, API, application, website, local file location, or other resource, you authorize Xoltra to access and act on that resource only within the permissions, scopes, and instructions you approve. You remain responsible for your relationship with the third party, its terms, its data, and all charges, consequences, and obligations associated with the connection.

Third-party services are not controlled by Xoltra. We do not endorse, guarantee, or assume responsibility for them. A third party may change, suspend, or terminate an integration, which may affect the Service.

8. Automation, Permissions, and Irreversible Actions

Automations can read, write, move, modify, delete, transmit, post, or otherwise act on data and external systems. You must review each workflow, node, permission request, scope, target, and proposed action before approving or running it. You must confirm that each action is lawful, authorized, appropriately scoped, and safe for the data and systems involved.

You are solely responsible for setting and maintaining least-privilege access, reviewing audit information where available, testing workflows in a non-production environment, and keeping suitable backups, approval controls, and human oversight. Do not enable automation for actions that could cause bodily injury, death, material financial loss, unlawful discrimination, loss of regulated data, irreversible system damage, or another high-impact outcome unless you have independently implemented appropriate safeguards and obtained our written approval where required.

Consent, scope checks, sandboxing, audit logs, permission prompts, and other controls are designed to support safer use; they are not a guarantee that an action is safe, authorized, correct, complete, or reversible. Revoking an integration or permission does not undo an action already performed, restore changed data, or eliminate third-party copies.

9. Acceptable Use

You must not, and must not allow anyone else to: violate law or another person's rights; submit unlawful, harmful, deceptive, infringing, defamatory, or privacy-invasive material; access or use the Service without authorization; bypass, disable, probe, or interfere with security controls, rate limits, consent flows, or access restrictions; use the Service to develop or distribute malware, destructive code, or credential theft; or use the Service to collect, scrape, or exfiltrate data without authorization.

You must not use the Service to impersonate another person, generate or deploy fraudulent content, conduct prohibited surveillance, make solely automated high-impact decisions about individuals, manipulate markets, facilitate violence or wrongdoing, or evade applicable export controls, sanctions, or sector-specific rules.

You must not reverse engineer, decompile, copy, modify, rent, lease, sell, resell, sublicense, or create derivative works of the Service except to the extent a restriction is prohibited by applicable law. You must not use the Service, Output, or documentation to build a competing service or train a competing model, except where we expressly permit it in writing.

10. Fees, Trials, and Taxes

If we offer paid plans, pricing, billing cadence, included usage, overages, cancellation rules, and any refund policy will be presented at checkout or in an applicable order form. You authorize us and our payment providers to charge the applicable fees and taxes using your chosen payment method. Fees are non-refundable except as required by law or expressly stated at purchase.

You are responsible for all taxes, duties, levies, and governmental charges associated with your use, excluding taxes based on our net income. We may change fees for a future billing period by giving advance notice through the Service or by email.

11. Xoltra Intellectual Property and Feedback

The Service, including its software, interfaces, workflow concepts, names, logos, documentation, and underlying technology, is owned by Xoltra or its licensors and is protected by intellectual-property laws. Subject to these Terms and payment of applicable fees, we grant you a limited, personal, non-exclusive, non-transferable, non-sublicensable, revocable right to use the Service during the applicable term.

If you provide suggestions, ideas, reports, or other feedback, you grant us a perpetual, irrevocable, worldwide, royalty-free right to use it without restriction or compensation.

12. Privacy and Security

Our Privacy Notice explains how we collect, use, retain, disclose, and protect personal data. It is incorporated into these Terms. Where applicable law requires a separate data-processing agreement, the parties will enter into one before processing covered data.

We use reasonable administrative, technical, and organizational measures appropriate to the Service, but no service, local system, network, integration, or transmission is completely secure. You must use reasonable security practices, including strong credentials, access reviews, device security, backups, and prompt revocation of compromised credentials.

13. Suspension and Termination

You may stop using the Service at any time. We may suspend or terminate access immediately if we reasonably believe you have violated these Terms, created a security or legal risk, failed to pay applicable fees, or if suspension is required by law or a third-party provider.

On termination, your right to use the Service ends. We may delete or de-identify Customer Content in accordance with our Privacy Notice, legal obligations, backup cycles, and applicable plan terms. Sections that by their nature should survive, including those concerning ownership, restrictions, disclaimers, limitation of liability, indemnity, disputes, and general terms, survive termination.

14. Disclaimers

TO THE MAXIMUM EXTENT PERMITTED BY LAW, THE SERVICE, OUTPUT, INTEGRATIONS, AND ALL RELATED MATERIALS ARE PROVIDED "AS IS" AND "AS AVAILABLE." XOLTRA AND ITS LICENSORS DISCLAIM ALL WARRANTIES, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, NON-INFRINGEMENT, ACCURACY, AVAILABILITY, SECURITY, AND QUIET ENJOYMENT.

WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, SECURE, AVAILABLE AT A PARTICULAR TIME, COMPATIBLE WITH EVERY SYSTEM, OR FREE FROM HARMFUL COMPONENTS; THAT OUTPUT WILL BE ACCURATE, COMPLETE, NON-INFRINGING, OR FIT FOR ANY PARTICULAR PURPOSE; OR THAT AUTOMATIONS WILL PRODUCE A PARTICULAR RESULT.

15. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, XOLTRA, ITS AFFILIATES, LICENSORS, SUPPLIERS, AND THEIR PERSONNEL WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, OR PUNITIVE DAMAGES, OR FOR ANY LOSS OF PROFITS, REVENUE, BUSINESS, DATA, GOODWILL, OR OPPORTUNITY, ARISING OUT OF OR RELATING TO THE SERVICE OR THESE TERMS, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

TO THE MAXIMUM EXTENT PERMITTED BY LAW, THE TOTAL LIABILITY OF XOLTRA AND ITS AFFILIATES, LICENSORS, SUPPLIERS, AND PERSONNEL FOR ALL CLAIMS ARISING OUT OF OR RELATING TO THE SERVICE OR THESE TERMS WILL NOT EXCEED THE GREATER OF (A) THE AMOUNTS YOU PAID TO XOLTRA FOR THE SERVICE IN THE TWELVE MONTHS BEFORE THE EVENT GIVING RISE TO THE CLAIM OR (B) US$100 (OR THE LOCAL-CURRENCY EQUIVALENT).

Nothing in these Terms excludes or limits liability that cannot lawfully be excluded or limited. Some jurisdictions do not permit certain exclusions or limitations, so some of this section may not apply to you.

16. Indemnity

To the maximum extent permitted by law, you will defend, indemnify, and hold harmless Xoltra, its affiliates, licensors, suppliers, and their personnel from and against claims, damages, losses, liabilities, costs, and expenses (including reasonable legal fees) arising from or relating to: your Customer Content; your use of the Service, Output, integrations, or automation; your violation of these Terms or law; your infringement or violation of another person's rights; or any action taken through your account or approved connection. We may assume control of the defense of a claim at your expense, and you will cooperate with us.

17. Governing Law and Disputes

These Terms and any dispute arising from them are governed by the laws of [GOVERNING LAW JURISDICTION], excluding its conflict-of-law rules. The courts located in [COURTS OR ARBITRATION VENUE] will have exclusive jurisdiction, and each party consents to their jurisdiction and venue, unless a mandatory consumer-protection law provides otherwise.

Before starting a formal dispute, the party raising the dispute must send a written notice to [LEGAL NOTICE EMAIL OR POSTAL ADDRESS] describing the claim and requested relief and allow thirty (30) days to attempt an informal resolution. You and Xoltra may agree in writing to resolve an eligible dispute by arbitration; any arbitration provision or class-action waiver must be reviewed and finalized for the jurisdiction in which Xoltra operates before publication.

18. General Terms

We may update these Terms from time to time. If a change is material, we will provide reasonable notice by posting the updated Terms, notifying you through the Service, or sending an email. The updated Terms take effect on the stated date. Your continued use after that date constitutes acceptance, except where applicable law requires a different process.

You may not assign or transfer these Terms without our prior written consent. We may assign these Terms in connection with a merger, acquisition, corporate reorganization, or sale of assets. Our failure to enforce a provision is not a waiver. If any provision is unenforceable, the remaining provisions remain in effect and the unenforceable provision will be enforced to the maximum lawful extent.

These Terms, the Privacy Notice, any applicable order form, and any other document expressly incorporated by reference are the entire agreement between you and Xoltra concerning the Service and replace prior agreements on that subject.

19. Contact

Questions about these Terms should be sent to Xoltraos@gmail.com. Legal notices to Xoltra must be sent to Achyuth_iyer@outlook.com.

Xoltra is operated by Xoltra.net, with its registered address at Xoltra, Bengaluru, Karnataka, 560001, India.

End of Terms of Service`;

export const PRIVACY_NOTICE_TEXT = `XOLTRA PRIVACY NOTICE
Effective date: July 13, 2026

1. Who This Notice Covers

This Privacy Notice explains how Xoltra ("Xoltra," "we," "us," or "our") collects, uses, discloses, retains, and protects information in connection with the Xoltra software, websites, applications, APIs, workflows, AI features, simulation features, integrations, and related services (collectively, the "Service"), as described in our Terms of Service. This Notice is incorporated into those Terms.

If you use the Service on behalf of an organization, this Notice covers information we collect about you as a user, in addition to any separate terms governing the organization's account.

2. Information We Collect

Account information. Email address, and, if you sign in with Google, your Google account email and basic profile information confirmed by Google at sign-in. If you register with a password instead, we store a salted, hashed version of it; we never store your password in plain text and cannot recover it.

Content you provide. Prompts, goals, chat messages, uploaded documents, workflow configurations, and instructions you give the Service ("Customer Content," as defined in the Terms).

Knowledge and context records. If you use features that retain context, such as saved goals, workflow plans, document-derived summaries, inferred patterns, or personalization traits learned from how you communicate, we store those records to provide continuity across sessions. These are stored in the storage environment associated with your deployment (locally, and/or in our cloud backup storage described in Section 6).

Automation and permission records. When you approve a workflow, integration, or automated action, we log what was requested, what scope or permission it required, and whether it was allowed, blocked, or required your consent. Workflow execution itself is processed through our automation engine (built on n8n); the data handled during a workflow run is limited to the scopes and connections you configure for that workflow. These audit records exist so you (and we) can see what an automation actually did.

Security and fraud-prevention signals. To protect accounts and the Service from abuse, we may collect: IP address, request patterns (used for rate limiting), a device fingerprint derived from browser and system characteristics (not a hardware identifier; no MAC address or similar hardware-level ID is collected), and results from bot-verification checks (Cloudflare Turnstile) performed at sign-in.

Connected third-party account data. If you connect a third-party account or service (for example, a cloud storage provider for premium backup, or another integration you approve), we access only the scopes and data you authorize, for the purposes you authorize.

Billing information. If you subscribe to a paid plan, our payment processor, [PAYMENT PROCESSOR NAME], collects and processes your payment details. We do not store full payment card numbers ourselves.

Technical and usage data. Log data, error reports, token/usage counts against your plan limits, timestamps, and similar operational data needed to run, secure, and improve the Service.

3. How We Use Information

We use the information above to:
• Provide, operate, and maintain the Service, including generating AI responses, building and running workflows, and retaining context you've asked us to retain
• Authenticate you, secure your account, and prevent fraud, abuse, and unauthorized access, including rate limiting, bot verification, and device-fingerprint-based abuse detection
• Enforce these policies and our Terms of Service, including, where a violation is confirmed, temporarily restricting account access
• Process payments and manage your subscription tier and usage limits
• Communicate with you about your account, security notices, or changes to the Service
• Maintain backups of your data so it can be restored if something is lost or corrupted
• Improve the Service, including understanding aggregate usage patterns

We do not sell your Customer Content or personal information.

4. AI Processing and Third-Party Model Providers

To generate responses, summaries, embeddings, and related Output, the Service transmits relevant portions of your prompts and Customer Content to our AI model provider, Cohere, and processes the results. Your use of AI features may also be subject to that provider's own applicable terms and processing practices.

We route requests to different models or processing steps depending on the nature of your request. We do not control how a third-party model provider was originally trained; do not submit personal, confidential, regulated, or highly sensitive information through the Service unless you are authorized to do so and our written agreement expressly permits that use, as described in the Terms.

5. Sharing and Disclosure

We share information only as follows:
• Service providers who help us operate the Service, including our AI model provider (Cohere), our workflow automation engine (n8n), cloud hosting and storage providers, our fraud-prevention/rate-limiting infrastructure provider, our bot verification provider (Cloudflare), and our payment processor. Each is bound to use the information only to provide their service to us
• Third-party accounts you connect: data flows only within the scopes and permissions you explicitly authorize when you connect an integration
• Legal and safety reasons: if required by law, legal process, or to protect the rights, property, or safety of Xoltra, our users, or others
• Business transfers: in connection with a merger, acquisition, reorganization, or sale of assets, as described in our Terms
• With your direction: any other sharing you explicitly request or authorize

6. Data Retention, Backups, and Deletion

We retain your account information and Customer Content for as long as your account is active, or as needed to provide the Service.

Knowledge and conversation records. Where the Service offers a deletion control (for example, deleting a saved chat or conversation), that action removes the associated knowledge records (goals, insights, and derived patterns tied to that conversation) from active storage. Deletion may not remove data that must be retained for security, legal, accounting, fraud-prevention, or backup-restoration purposes, consistent with our Terms.

Backups. We maintain periodic backup snapshots of the data associated with your account so it can be restored if the primary copy is lost, corrupted, or otherwise unavailable. Backup snapshots are retained on a rolling basis and are not immediately purged when you delete something from active storage; they age out according to our backup retention schedule.

Premium cloud storage backup (OneDrive). If you are on a plan that offers backing up your Xoltra data to a connected OneDrive account, that data is written to storage you control within your own Microsoft account, governed by Microsoft's own terms and privacy practices in addition to this Notice. Disconnecting OneDrive stops future backups but does not delete files already written there; you control deletion of that copy directly through your Microsoft account.

Account timeout and moderation records. If an account is temporarily restricted for a Terms of Service violation, we retain a record of the restriction (reason, duration, and issuing action) for accountability and appeal purposes, even after the restriction itself expires.

7. Security

We use administrative, technical, and organizational measures appropriate to the Service, including encrypted password storage, signed and authenticated internal service requests, permission-scoped automation controls, rate limiting, and bot verification. No service, local system, network, integration, or transmission is completely secure. You are responsible for using reasonable security practices on your end, including strong credentials and prompt revocation of compromised credentials, as described in our Terms.

8. Governing Framework and Cross-Border Transfers

This Notice, and our processing of personal data, is designed with reference to India's Digital Personal Data Protection Act, 2023 ("DPDP Act") and the Digital Personal Data Protection Rules, 2025 ("DPDP Rules"), notified on November 13, 2025. Under this framework, Xoltra acts as a "Data Fiduciary" and you, as a user, are a "Data Principal."

The DPDP Act and Rules are being brought into force in phases; certain provisions took effect from November 13, 2025, Consent Manager registration provisions take effect from November 13, 2026, and the remaining provisions, including standalone consent-notice, rights, and security requirements, take full effect from May 13, 2027.

Xoltra is operated by Xoltra.net, based in Bengaluru, Karnataka, India. Depending on the service providers described in Section 5 (for example, our AI model provider, workflow automation engine, cloud hosting, and payment processor), your information may be processed or stored outside India. The DPDP Act permits cross-border transfer of personal data by default, except to countries or territories notified as restricted by the Central Government from time to time. We do not transfer personal data to any country notified as restricted under the DPDP Act.

9. Your Rights as a Data Principal

Subject to the DPDP Act, the DPDP Rules, and their phased commencement described in Section 8, you have the right to:
• Access a summary of the personal data we hold about you and the processing activities we carry out on it
• Correction and completion of inaccurate or incomplete personal data
• Erasure of personal data that is no longer necessary for the purpose it was collected, subject to our right and, in some cases, legal obligation to retain certain data as described in Section 6
• Grievance redressal, as described in Section 9A below, before approaching the Data Protection Board of India
• Nominate another individual to exercise these rights on your behalf in the event of your death or incapacity, where the DPDP Rules make this available
• Withdraw consent at any time where our processing is based on your consent, without affecting the lawfulness of processing carried out before withdrawal

To exercise these rights, contact us at [PRIVACY CONTACT EMAIL]. We may need to verify your identity before acting on a request. Where the Service provides an in-product control, such as deleting a conversation or disconnecting an integration, using that control is the fastest way to act on your own data directly.

9A. Grievance Officer

In accordance with the DPDP Act and DPDP Rules, complaints or grievances regarding the processing of your personal data may be directed to our Grievance Officer:
[GRIEVANCE OFFICER NAME]
Xoltra.net, Bengaluru, Karnataka, 560001, India
Email: [GRIEVANCE OFFICER EMAIL]

We will acknowledge and address grievances within [RESPONSE TIMELINE]. If you are not satisfied with our response, you may escalate your grievance to the Data Protection Board of India.

10. Children's Privacy

The Service is not directed to, and may not be used by, anyone under 18 years old, consistent with the eligibility requirement in our Terms of Service. Under the DPDP Act, an individual under 18 is a "child," and processing a child's personal data requires verifiable consent from a parent or lawful guardian. Because the Service is not offered to individuals under 18, we do not knowingly collect personal data from children. If we learn that we have collected data from someone under 18, we will take steps to delete it.

11. Changes to This Notice

We may update this Notice from time to time. If a change is material, we will provide reasonable notice by posting the updated Notice, notifying you through the Service, or sending an email, consistent with how we handle material changes to our Terms of Service. The updated Notice takes effect on the stated effective date.

12. Contact Us

Questions about this Privacy Notice should be sent to xoltraos@gmail.com. Legal notices to Xoltra must be sent to xoltralegalteam@gmail.com.

Xoltra is operated by Xoltra.net, with its registered address at Xoltra, Bengaluru, Karnataka, 560001, India.

End of Privacy Notice`;
