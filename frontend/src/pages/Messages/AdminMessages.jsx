import React, { useState, useEffect, useRef } from "react";
import api from "../../store/api";

export default function AdminMessages() {
  const [tab, setTab] = useState("conversations"); // "conversations" | "contact-forms"

  // ── Conversations state ──
  const [conversations, setConversations] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [content, setContent] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef(null);

  // ── Contact forms state ──
  const [contactForms, setContactForms] = useState([]);
  const [contactLoading, setContactLoading] = useState(false);
  const [selectedContact, setSelectedContact] = useState(null);

  // ── Fetch conversations ──
  const fetchConversations = async () => {
    try {
      const res = await api.get("/messages/admin/conversations");
      setConversations(res.data.conversations || []);
    } catch (err) {
      console.error("Failed to fetch conversations:", err);
    } finally {
      setLoading(false);
    }
  };

  // ── Fetch contact forms ──
  const fetchContactForms = async () => {
    setContactLoading(true);
    try {
      const res = await api.get("/messages/admin/contact-forms");
      setContactForms(res.data.messages || []);
    } catch (err) {
      console.error("Failed to fetch contact forms:", err);
    } finally {
      setContactLoading(false);
    }
  };

  const fetchMessages = async (userId) => {
    try {
      const res = await api.get(`/messages/admin/conversation/${userId}`);
      setMessages(res.data.messages || []);
    } catch (err) {
      console.error("Failed to fetch messages:", err);
    }
  };

  const selectUser = async (conv) => {
    setSelectedUser(conv);
    await fetchMessages(conv.user_id);
    setConversations(prev =>
      prev.map(c => c.user_id === conv.user_id ? { ...c, unread: 0 } : c)
    );
  };

  const sendReply = async () => {
    if (!content.trim() || !selectedUser) return;
    setSending(true);
    try {
      await api.post(`/messages/admin/reply/${selectedUser.user_id}`, { content });
      setContent("");
      await fetchMessages(selectedUser.user_id);
    } catch (err) {
      alert("Failed to send reply.");
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendReply();
    }
  };

  useEffect(() => {
    fetchConversations();
    const interval = setInterval(fetchConversations, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (tab === "contact-forms") fetchContactForms();
  }, [tab]);

  useEffect(() => {
    if (selectedUser) {
      const interval = setInterval(() => fetchMessages(selectedUser.user_id), 10000);
      return () => clearInterval(interval);
    }
  }, [selectedUser]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const totalUnread = conversations.reduce((s, c) => s + (c.unread || 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)" }}>

      {/* ── Tabs ── */}
      <div style={{
        display: "flex",
        borderBottom: "1px solid #e2e8f0",
        background: "#fff",
        padding: "0 20px",
      }}>
        <button
          onClick={() => setTab("conversations")}
          style={{
            padding: "14px 18px",
            border: "none",
            background: "none",
            cursor: "pointer",
            fontSize: 14,
            fontWeight: tab === "conversations" ? 700 : 500,
            color: tab === "conversations" ? "#2563eb" : "#64748b",
            borderBottom: tab === "conversations" ? "2px solid #2563eb" : "2px solid transparent",
            display: "flex",
            alignItems: "center",
            gap: 8,
            transition: "color 0.15s",
          }}
        >
          User Conversations
          {totalUnread > 0 && (
            <span style={{
              background: "#2563eb", color: "white",
              borderRadius: 10, padding: "1px 7px",
              fontSize: 11, fontWeight: 700,
            }}>{totalUnread}</span>
          )}
        </button>

        <button
          onClick={() => setTab("contact-forms")}
          style={{
            padding: "14px 18px",
            border: "none",
            background: "none",
            cursor: "pointer",
            fontSize: 14,
            fontWeight: tab === "contact-forms" ? 700 : 500,
            color: tab === "contact-forms" ? "#2563eb" : "#64748b",
            borderBottom: tab === "contact-forms" ? "2px solid #2563eb" : "2px solid transparent",
            display: "flex",
            alignItems: "center",
            gap: 8,
            transition: "color 0.15s",
          }}
        >
          Contact Forms
          {contactForms.length > 0 && (
            <span style={{
              background: "#64748b", color: "white",
              borderRadius: 10, padding: "1px 7px",
              fontSize: 11, fontWeight: 700,
            }}>{contactForms.length}</span>
          )}
        </button>
      </div>

      {/* ── Tab: Conversations ── */}
      {tab === "conversations" && (
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* Sidebar */}
          <div style={{
            width: 280,
            borderRight: "1px solid #e2e8f0",
            overflowY: "auto",
            background: "#f8fafc",
          }}>
            <div style={{ padding: "16px 16px 12px", borderBottom: "1px solid #e2e8f0" }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0 }}>User conversations</h2>
            </div>

            {loading ? (
              <div style={{ padding: 20, color: "#94a3b8", fontSize: 13 }}>Loading...</div>
            ) : conversations.length === 0 ? (
              <div style={{ padding: 20, color: "#94a3b8", fontSize: 13 }}>No conversations yet.</div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.user_id}
                  onClick={() => selectUser(conv)}
                  style={{
                    padding: "12px 16px",
                    cursor: "pointer",
                    background: selectedUser?.user_id === conv.user_id ? "#eff6ff" : "transparent",
                    borderBottom: "1px solid #f1f5f9",
                    borderLeft: selectedUser?.user_id === conv.user_id ? "3px solid #2563eb" : "3px solid transparent",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => {
                    if (selectedUser?.user_id !== conv.user_id)
                      e.currentTarget.style.background = "#f1f5f9";
                  }}
                  onMouseLeave={(e) => {
                    if (selectedUser?.user_id !== conv.user_id)
                      e.currentTarget.style.background = "transparent";
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 14, color: "#0f172a" }}>{conv.username}</span>
                    {conv.unread > 0 && (
                      <span style={{
                        background: "#2563eb", color: "white",
                        borderRadius: 10, padding: "2px 7px",
                        fontSize: 11, fontWeight: 700,
                      }}>{conv.unread}</span>
                    )}
                  </div>
                  {conv.last_message && (
                    <p style={{
                      margin: "4px 0 0", fontSize: 12, color: "#64748b",
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                    }}>{conv.last_message}</p>
                  )}
                  {conv.last_time && (
                    <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>
                      {new Date(conv.last_time).toLocaleString()}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Chat area */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            {!selectedUser ? (
              <div style={{
                flex: 1, display: "flex", alignItems: "center",
                justifyContent: "center", color: "#94a3b8", fontSize: 14,
              }}>
                Select a conversation to start messaging
              </div>
            ) : (
              <>
                <div style={{
                  padding: "16px 20px", borderBottom: "1px solid #e2e8f0",
                  background: "#fff", display: "flex", alignItems: "center", gap: 10,
                }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: "50%",
                    background: "#eff6ff", color: "#2563eb",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontWeight: 700, fontSize: 14,
                  }}>
                    {selectedUser.username[0].toUpperCase()}
                  </div>
                  <span style={{ fontWeight: 600, fontSize: 15, color: "#0f172a" }}>
                    {selectedUser.username}
                  </span>
                </div>

                <div style={{
                  flex: 1, overflowY: "auto", padding: 16,
                  display: "flex", flexDirection: "column", gap: 10, background: "#f8fafc",
                }}>
                  {messages.length === 0 ? (
                    <div style={{ textAlign: "center", color: "#94a3b8", fontSize: 14, marginTop: 40 }}>
                      No messages yet.
                    </div>
                  ) : (
                    messages.map((msg) => (
                      <div key={msg.message_id} style={{
                        display: "flex",
                        justifyContent: msg.is_mine ? "flex-end" : "flex-start",
                      }}>
                        <div style={{
                          maxWidth: "70%", padding: "10px 14px",
                          borderRadius: msg.is_mine ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                          background: msg.is_mine ? "#2563eb" : "#fff",
                          color: msg.is_mine ? "white" : "#0f172a",
                          border: msg.is_mine ? "none" : "1px solid #e2e8f0",
                          fontSize: 14, lineHeight: 1.5,
                          boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                        }}>
                          <p style={{ margin: 0 }}>{msg.content}</p>
                          <p style={{ margin: "4px 0 0", fontSize: 11, opacity: 0.7, textAlign: "right" }}>
                            {new Date(msg.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                  <div ref={bottomRef} />
                </div>

                <div style={{
                  padding: "12px 16px", borderTop: "1px solid #e2e8f0",
                  background: "#fff", display: "flex", gap: 10,
                }}>
                  <textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type your reply... (Enter to send)"
                    rows={2}
                    style={{
                      flex: 1, padding: "10px 14px", borderRadius: 10,
                      border: "1px solid #e2e8f0", fontSize: 14,
                      resize: "none", outline: "none",
                      fontFamily: "inherit", color: "#0f172a",
                    }}
                  />
                  <button
                    onClick={sendReply}
                    disabled={sending || !content.trim()}
                    style={{
                      padding: "0 20px", borderRadius: 10, border: "none",
                      background: sending || !content.trim() ? "#93c5fd" : "#2563eb",
                      color: "white", fontSize: 14, fontWeight: 600,
                      cursor: sending || !content.trim() ? "not-allowed" : "pointer",
                    }}
                  >
                    {sending ? "..." : "Reply"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Contact Forms ── */}
      {tab === "contact-forms" && (
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* List */}
          <div style={{
            width: 300,
            borderRight: "1px solid #e2e8f0",
            overflowY: "auto",
            background: "#f8fafc",
          }}>
            <div style={{ padding: "16px 16px 12px", borderBottom: "1px solid #e2e8f0" }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0 }}>Contact forms</h2>
              <p style={{ fontSize: 12, color: "#64748b", margin: "4px 0 0" }}>
                {contactForms.length} message{contactForms.length !== 1 ? "s" : ""}
              </p>
            </div>

            {contactLoading ? (
              <div style={{ padding: 20, color: "#94a3b8", fontSize: 13 }}>Loading...</div>
            ) : contactForms.length === 0 ? (
              <div style={{ padding: 20, color: "#94a3b8", fontSize: 13 }}>No contact form messages.</div>
            ) : (
              contactForms.map((cf) => (
                <div
                  key={cf.message_id}
                  onClick={() => setSelectedContact(cf)}
                  style={{
                    padding: "12px 16px",
                    cursor: "pointer",
                    background: selectedContact?.message_id === cf.message_id ? "#eff6ff" : "transparent",
                    borderBottom: "1px solid #f1f5f9",
                    borderLeft: selectedContact?.message_id === cf.message_id ? "3px solid #2563eb" : "3px solid transparent",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => {
                    if (selectedContact?.message_id !== cf.message_id)
                      e.currentTarget.style.background = "#f1f5f9";
                  }}
                  onMouseLeave={(e) => {
                    if (selectedContact?.message_id !== cf.message_id)
                      e.currentTarget.style.background = "transparent";
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 14, color: "#0f172a" }}>{cf.name}</span>
                    <span style={{ fontSize: 11, color: "#94a3b8" }}>
                      {new Date(cf.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p style={{ margin: "3px 0 0", fontSize: 12, color: "#64748b" }}>{cf.email}</p>
                  <p style={{
                    margin: "4px 0 0", fontSize: 12, color: "#94a3b8",
                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                  }}>{cf.message}</p>
                </div>
              ))
            )}
          </div>

          {/* Detail */}
          <div style={{ flex: 1, padding: 24, overflowY: "auto", background: "#fff" }}>
            {!selectedContact ? (
              <div style={{
                height: "100%", display: "flex", alignItems: "center",
                justifyContent: "center", color: "#94a3b8", fontSize: 14,
              }}>
                Select a message to view details
              </div>
            ) : (
              <div style={{ maxWidth: 600 }}>
                <div style={{
                  background: "#f8fafc", borderRadius: 12,
                  padding: 20, border: "1px solid #e2e8f0", marginBottom: 20,
                }}>
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                    <div>
                      <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 2px", textTransform: "uppercase", letterSpacing: 0.5 }}>From</p>
                      <p style={{ fontSize: 15, fontWeight: 600, color: "#0f172a", margin: 0 }}>{selectedContact.name}</p>
                    </div>
                    <div>
                      <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 2px", textTransform: "uppercase", letterSpacing: 0.5 }}>Email</p>
                      <a href={`mailto:${selectedContact.email}`} style={{ fontSize: 14, color: "#2563eb", margin: 0 }}>
                        {selectedContact.email}
                      </a>
                    </div>
                    <div>
                      <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 2px", textTransform: "uppercase", letterSpacing: 0.5 }}>Date</p>
                      <p style={{ fontSize: 14, color: "#475569", margin: 0 }}>
                        {new Date(selectedContact.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>

                <div style={{
                  background: "#fff", borderRadius: 12,
                  padding: 20, border: "1px solid #e2e8f0",
                }}>
                  <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 10px", textTransform: "uppercase", letterSpacing: 0.5 }}>Message</p>
                  <p style={{ fontSize: 14, color: "#0f172a", lineHeight: 1.7, margin: 0, whiteSpace: "pre-wrap" }}>
                    {selectedContact.message}
                  </p>
                </div>

                <a
                  href={`mailto:${selectedContact.email}?subject=Re: Your HPC Portal message`}
                  style={{
                    display: "inline-block", marginTop: 16,
                    padding: "10px 20px", borderRadius: 8,
                    background: "#2563eb", color: "white",
                    fontSize: 14, fontWeight: 600,
                    textDecoration: "none",
                  }}
                >
                  Reply via Email
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
