import { DocumentWorkspace } from "./DocumentWorkspace";

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DocumentWorkspace jobId={id} />;
}
