# secure-api

Encrypted key-value data store (`/v1/data/:key`) with signature-based auth.

STATUS: not currently called by the Flask backend or the Next.js frontend.
The only thing that exercises this service today is scan.js's own security
probe. Confirm whether this is still needed before relying on it in new work.

Dropped `cors` and `dotenv` from the original dependency list — grepped
server.js and neither is actually required anywhere in it.
