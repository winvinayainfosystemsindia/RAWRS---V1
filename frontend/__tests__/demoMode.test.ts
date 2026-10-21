import { api, demoFile, DEMO_JOB_ID } from "@/lib/api";

const fetchMock = jest.fn();
beforeEach(() => {
  fetchMock.mockReset().mockResolvedValue({ ok: true, json: async () => ({ job_id: DEMO_JOB_ID }) });
  global.fetch = fetchMock;
});

test("maps demo-document API paths to the captured static files", () => {
  expect(demoFile("/api/documents/demo")).toBe("/demo/index.json");
  expect(demoFile("/api/documents/demo/reading-order")).toBe("/demo/reading-order.json");
  expect(demoFile("/api/documents/demo/corrections?status=pending")).toBe("/demo/corrections.json");
  expect(demoFile("/api/documents/demo2/tables")).toBeNull();
  expect(demoFile("/api/documents/abc123/tables")).toBeNull();
  expect(demoFile("/api/ai/status")).toBeNull();
});

test("reads the sample document from static files, never the backend", async () => {
  await api.getDocument(DEMO_JOB_ID);
  await api.getTables(DEMO_JOB_ID);
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/demo/index.json", "/demo/tables.json"]);

  expect(api.sourcePdfUrl(DEMO_JOB_ID)).toBe("/demo/source.pdf");
  expect(api.imageUrl(DEMO_JOB_ID, "img1")).toBe("/demo/images/img1");
  expect(api.fileUrl("/api/documents/demo/images/img1/file")).toBe("/demo/images/img1");
  expect(api.fileUrl("/api/documents/abc123/images/img1/file")).toMatch(/^http.*\/api\/documents\/abc123\/images\/img1\/file$/);
  expect(api.downloadUrl(DEMO_JOB_ID, "docx")).toBe("/demo/download/document.docx");
});

test("refuses every edit to the sample document without a network call", async () => {
  const edits = [
    api.saveMarkdown(DEMO_JOB_ID, "x"),
    api.reviewHeading(DEMO_JOB_ID, 1, { action: "accept" } as never),
    api.uploadFinalDocx(DEMO_JOB_ID, new File(["x"], "f.docx")),
    api.deleteTable(DEMO_JOB_ID, "t1"),
    api.previewDocx(DEMO_JOB_ID, "x"),
  ];
  for (const edit of edits) await expect(edit).rejects.toMatchObject({ status: 403 });
  expect(fetchMock).not.toHaveBeenCalled();
});

test("other documents still go to the backend", async () => {
  await api.getDocument("abc123");
  expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/documents\/abc123$/);
});
