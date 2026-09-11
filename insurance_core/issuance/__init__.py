"""Policy issuance building blocks: numbering, signing, policy records and PDF certificates.

Nothing here touches a database or the file system. The backend's issuance service
combines these pieces inside a database transaction.
"""