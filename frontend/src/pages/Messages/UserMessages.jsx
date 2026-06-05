import React, { useState, useEffect, useRef } from "react";
import api from "../../store/api";

export default function UserMessages() {
  const [messages, setMessages] = useState([]);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  const fetchMessages = async () => {
    try {
      const res = await api.get("/messages/my-conversation");
      setMessages(res.data.messages || []);
    } catch (err) {
      console.error("Failed to fetch messages:", err);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!content.trim()) return;
    setSending(true);
    try {
      await api.post("/messages/send", { content });
      setContent("");
      await fetchMessages();
    } catch (err) {
      alert("Failed to send message.");
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  useEffect(() => {
    fetchMessages();
    const interval = setInterval(fetchMessages, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (loading) return <div style={{ padding: 30, color: "#64748b" }}>Loading messages...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)", maxWidth: 720, margin: "0 auto", padding: "24px 16px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", marginBottom: 4 }}>Messages</h1>
      <p style={{ fontSize: 13, color: "#64748b", marginBottom: 20 }}>Your conversation with the admin team.</p>

      {/* Chat box */}
      <div style={{
        flex: 1,
        overflowY: "auto",
        background: "#f8fafc",
        borderRadius: 12,
        border: "1px solid #e2e8f0",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        marginBottom: 16,
      }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: "center", color: "#94a3b8", fontSize: 14, marginTop: 40 }}>
            No messages yet. Send a message to the admin team.
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.message_id} style={{
              display: "flex",
              justifyContent: msg.is_mine ? "flex-end" : "flex-start",
            }}>
              <div style={{
                maxWidth: "70%",
                padding: "10px 14px",
                borderRadius: msg.is_mine ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                background: msg.is_mine ? "#2563eb" : "#fff",
                color: msg.is_mine ? "white" : "#0f172a",
                border: msg.is_mine ? "none" : "1px solid #e2e8f0",
                fontSize: 14,
                lineHeight: 1.5,
                boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
              }}>
                <p style={{ margin: 0 }}>{msg.content}</p>
                <p style={{
                  margin: "4px 0 0",
                  fontSize: 11,
                  opacity: 0.7,
                  textAlign: "right",
                }}>
                  {new Date(msg.created_at).toLocaleString()}
                </p>
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: 10 }}>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Enter to send)"
          rows={2}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #e2e8f0",
            fontSize: 14,
            resize: "none",
            outline: "none",
            fontFamily: "inherit",
            color: "#0f172a",
          }}
        />
        <button
          onClick={sendMessage}
          disabled={sending || !content.trim()}
          style={{
            padding: "0 20px",
            borderRadius: 10,
            border: "none",
            background: sending || !content.trim() ? "#93c5fd" : "#2563eb",
            color: "white",
            fontSize: 14,
            fontWeight: 600,
            cursor: sending || !content.trim() ? "not-allowed" : "pointer",
          }}
        >
          {sending ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
