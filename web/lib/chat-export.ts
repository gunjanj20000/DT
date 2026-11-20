import {
  exportCoWriterDocx,
  exportCoWriterPdf,
  exportCoWriterEpub,
} from "@/lib/co-writer-api";

/**
 * Minimal message/attachment shape the markdown exporter needs. Product chat's
 * `MessageItem` satisfies it structurally, and partner conversations map into
 * it too — so both surfaces share one serializer.
 */
export interface ExportableAttachment {
  type?: string;
  filename?: string;
  mime_type?: string;
}

export interface ExportableMessage {
  role: string;
  content: string;
  /** Optional human-readable author for multi-speaker conversations. */
  speaker?: string;
  capability?: string;
  attachments?: ExportableAttachment[];
}

function roleHeading(role: string): string {
  if (role === "user") return "User";
  if (role === "assistant") return "Assistant";
  return "System";
}

function messageHeading(message: ExportableMessage): string {
  // Keep an untrusted display name on one Markdown heading line. Markdown
  // punctuation is harmless here, but line breaks could forge extra blocks.
  const speaker = message.speaker?.trim().replace(/\s+/g, " ");
  return speaker || roleHeading(message.role);
}

function formatAttachments(attachments?: ExportableAttachment[]): string {
  if (!attachments?.length) return "";
  const items = attachments
    .map((a) => {
      const name = a.filename || a.type || "attachment";
      return a.mime_type ? `\`${name}\` (${a.mime_type})` : `\`${name}\``;
    })
    .join(", ");
  return `_Attachments:_ ${items}\n\n`;
}

export interface BuildChatMarkdownOptions {
  title?: string;
  exportedAt?: Date;
}

export function buildChatMarkdown(
  messages: ExportableMessage[],
  options: BuildChatMarkdownOptions = {},
): string {
  const title = options.title?.trim() || "Chat Session";
  const exportedAt = (options.exportedAt ?? new Date()).toISOString();
  const header = `# ${title}\n\n_Exported: ${exportedAt}_\n\n---\n\n`;
  const body = messages
    .map((msg) => {
      const role = messageHeading(msg);
      const cap = msg.capability ? ` _(${msg.capability})_` : "";
      const attachments = formatAttachments(msg.attachments);
      const content = (msg.content ?? "").trim();
      return `## ${role}${cap}\n\n${attachments}${content}`.trimEnd();
    })
    .join("\n\n---\n\n");
  return header + body + "\n";
}

function sanitizeFilename(input: string): string {
  const cleaned = input
    .replace(/[\\/:*?"<>|\n\r\t]/g, "")
    .replace(/\s+/g, "-")
    .slice(0, 60);
  return cleaned || "chat";
}

export function downloadChatMarkdown(
  messages: ExportableMessage[],
  options: BuildChatMarkdownOptions = {},
): void {
  if (!messages.length) return;
  const markdown = buildChatMarkdown(messages, options);
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const date = new Date().toISOString().slice(0, 10);
  anchor.download = `${sanitizeFilename(options.title || "chat")}-${date}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function downloadChatPdf(
  messages: ExportableMessage[],
  options: BuildChatMarkdownOptions = {},
): Promise<void> {
  if (!messages.length) return;
  const title = options.title?.trim() || "Chat Session";
  const markdown = buildChatMarkdown(messages, options);
  const blob = await exportCoWriterPdf({ title, content: markdown });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const date = new Date().toISOString().slice(0, 10);
  anchor.download = `${sanitizeFilename(title)}-${date}.pdf`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadChatEpub(
  messages: ExportableMessage[],
  options: BuildChatMarkdownOptions = {},
): Promise<void> {
  if (!messages.length) return;
  const title = options.title?.trim() || "Chat Session";
  const markdown = buildChatMarkdown(messages, options);
  const blob = await exportCoWriterEpub({ title, content: markdown });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const date = new Date().toISOString().slice(0, 10);
  anchor.download = `${sanitizeFilename(title)}-${date}.epub`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadSingleMessage(
  message: ExportableMessage,
  format: "md" | "docx" | "pdf" | "epub",
  title?: string,
): Promise<void> {
  const content = (message.content || "").trim();
  if (!content) return;
  const docTitle = (title || "DeepTutor Answer").trim();
  const date = new Date().toISOString().slice(0, 10);
  const safeName = `${sanitizeFilename(docTitle)}-${date}`;

  let blob: Blob;
  if (format === "md") {
    blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  } else if (format === "docx") {
    blob = await exportCoWriterDocx({ title: docTitle, content });
  } else if (format === "pdf") {
    blob = await exportCoWriterPdf({ title: docTitle, content });
  } else {
    blob = await exportCoWriterEpub({ title: docTitle, content });
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeName}.${format}`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
