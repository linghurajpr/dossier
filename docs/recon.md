# Cominty SDK recon summary

- **PASS [1] Auth + basic run:** basic run completed; text='Pong! How can I help you today?' (elapsed 2.847s)
- **PASS [2] Event shape:** iterated 7 event(s) and read reply
- **PASS [3] File upload:** uploaded sample.pdf; text='Document title: "Contrat de location - SPECIMEN"; monthly rent: 850,00 EUR.' (elapsed 6.023s)
- **PASS [4] Structured output:** json.loads(text) worked directly: '{"ok": true, "n": 3}'
- **PASS [5] Multi-file message:** uploaded two files and sent both IDs; text='Both attached files are identical (same MD5 checksum), so the answer is the same for each:\n\n- **Document title:** "Contrat de location - SPECIMEN" (English: "Lease agreement - SPECIMEN")\n- **Rent amount:** 850,00 EUR per month ("Loyer mensuel : 850,00 EUR")\n\nThe document also notes that its data is synthetic test data. The PDF metadata title is "untitled," so the title above comes from the visible text on the page.'
- **PASS [6] Memory:** memory round-trip at recon/1793832723150267000.txt; value=MemoryFileOut(path='recon/1793832723150267000.txt', namespace='dossier-recon', purpose='Cominty SDK recon probe', content='recon memory round-trip', created_at=datetime.datetime(2026, 11, 4, 22, 52, 3, 219005, tzinfo=TzInfo(0)), updated_at=datetime.datetime(2026, 11, 4, 22, 52, 3, 219005, tzinfo=TzInfo(0)), version='2026-11-04T22:52:03.219005Z')
- **PASS [7] Approval API:** present: reply.status
- **MISSING [8] Usage data:** found 0 usage-related attribute(s)
- **PASS [9] Latency:** probe 1: 2.847s; probe 3: 6.023s

- **chat.start calls:** 5
- **chat.send calls:** 0
- **total calls:** 5
