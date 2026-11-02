import { useCallback, useEffect, useRef, useState } from 'react';
import { desktop, request } from '../lib/bridge';
import { mergeMessages, syncLatest } from '../lib/chatMessages';
import type { ChatDialogs, ChatHistory, ChatMessage, Connection, TelegramChat } from '../types';

const describe = (error: unknown) => String(error instanceof Error ? error.message : error);

export function useChats(connection: Connection) {
  const connected = desktop && connection === 'connected';
  const [chats, setChats] = useState<TelegramChat[]>([]);
  const [dialogsMore, setDialogsMore] = useState(false);
  const [dialogsOffset, setDialogsOffset] = useState(0);
  const [listing, setListing] = useState(false);
  const [listError, setListError] = useState('');
  const [selected, setSelected] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [historyMore, setHistoryMore] = useState(false);
  const [before, setBefore] = useState<number | null>(null);
  const [reading, setReading] = useState(false);
  const [sending, setSending] = useState(false);
  const [readError, setReadError] = useState('');
  const [sendError, setSendError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const current = useRef(selected);
  const mounted = useRef(true);
  const session = useRef(0);
  const listingLock = useRef(false);
  const sendLock = useRef(false);
  const historyLock = useRef(false);
  const loadedOlder = useRef(false);
  current.current = selected;

  const loadDialogs = useCallback(async (offset = 0) => {
    if (!connected || listingLock.current) return;
    listingLock.current = true;
    setListing(true);
    setListError('');
    const version = session.current;
    try {
      const result = await request<ChatDialogs>('chat_dialogs', { offset });
      if (mounted.current && version === session.current) {
        setChats(previous => offset ? [...new Map([...previous, ...result.chats].map(chat => [chat.id, chat])).values()] : result.chats);
        setDialogsMore(result.has_more);
        setDialogsOffset(result.next_offset);
      }
    } catch (error) {
      if (mounted.current && version === session.current) setListError(describe(error));
    } finally {
      if (version === session.current) {
        listingLock.current = false;
        if (mounted.current) setListing(false);
      }
    }
  }, [connected]);

  useEffect(() => {
    mounted.current = true;
    session.current += 1;
    listingLock.current = false;
    setListing(false);
    if (connected) void loadDialogs();
    else {
      setChats([]); setSelected(''); setMessages([]); setDialogsMore(false);
      setListError(''); setReadError(''); setSendError('');
    }
    return () => { mounted.current = false; session.current += 1; };
  }, [connected, loadDialogs]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const version = session.current;
    loadedOlder.current = false;
    setMessages([]); setBefore(null); setHistoryMore(false); setReadError(''); setSendError('');
    if (!connected || !selected) { setReading(false); return; }
    const valid = () => !stopped && mounted.current && version === session.current && current.current === selected;
    async function poll() {
      if (!valid()) return;
      if (sendLock.current || historyLock.current) { timer = setTimeout(poll, 1000); return; }
      historyLock.current = true;
      setReading(true);
      try {
        const result = await request<ChatHistory>('chat_history', { chat_id: selected });
        if (valid()) {
          setMessages(previous => syncLatest(previous, result.messages));
          if (!loadedOlder.current) { setBefore(result.next_before); setHistoryMore(result.has_more); }
          setReadError('');
          timer = setTimeout(poll, 5000);
        }
      } catch (error) {
        // Leave errors visible and pause polling until the user refreshes.
        if (valid()) setReadError(describe(error));
      } finally {
        historyLock.current = false;
        if (valid()) setReading(false);
      }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [connected, selected, refreshKey]);

  const loadOlder = useCallback(async () => {
    if (!connected || !selected || !before || historyLock.current || sendLock.current) return;
    historyLock.current = true;
    setReading(true); setReadError('');
    const target = selected;
    const version = session.current;
    try {
      const result = await request<ChatHistory>('chat_history', { chat_id: target, before });
      if (mounted.current && version === session.current && current.current === target) {
        loadedOlder.current = true;
        setMessages(previous => mergeMessages(previous, result.messages));
        setBefore(result.next_before); setHistoryMore(result.has_more);
      }
    } catch (error) {
      if (mounted.current && version === session.current && current.current === target) setReadError(describe(error));
    } finally {
      historyLock.current = false;
      if (mounted.current) setReading(false);
    }
  }, [connected, selected, before]);

  const send = useCallback(async (target: string, text: string, style: string) => {
    if (!connected || sendLock.current) return false;
    sendLock.current = true;
    setSending(true); setSendError('');
    const version = session.current;
    try {
      const result = await request<{ chat_id: string; message: ChatMessage }>('chat_send', { chat_id: target, text, style });
      if (mounted.current && version === session.current) {
        if (current.current === target) setMessages(previous => mergeMessages(previous, [result.message]));
        setChats(previous => previous.map(chat => chat.id === target ? { ...chat, preview: result.message.text, date: result.message.date } : chat));
      }
      return true;
    } catch (error) {
      if (mounted.current && version === session.current) setSendError(describe(error));
      return false;
    } finally {
      sendLock.current = false;
      if (mounted.current) setSending(false);
    }
  }, [connected]);

  const select = useCallback((id: string) => {
    if (id === current.current) return;
    current.current = id;
    setSelected(id); setMessages([]); setBefore(null); setHistoryMore(false);
    setReadError(''); setSendError(''); setReading(connected);
  }, [connected]);

  return {
    chats, selected, select, messages, listing, reading, sending, listError, readError, sendError,
    dialogsMore, historyMore, refreshDialogs: () => loadDialogs(), loadMoreDialogs: () => loadDialogs(dialogsOffset),
    refreshMessages: () => setRefreshKey(value => value + 1), loadOlder, send,
  };
}
