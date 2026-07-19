import React, { useState, useEffect } from 'react';

// API Base URL config
const API_URL = 'http://localhost:8000';

interface BacklogItem {
  id: string;
  meeting_id: string;
  type: string;
  title: string;
  description: string;
  acceptance_criteria: string[];
  story_points: number;
  priority: number;
  approved: number;
  tags: string[];
  azure_id: string | null;
}

interface Meeting {
  id: string;
  title: string;
  transcript: string;
  summary: string;
  decisions: string[];
  risks: string[];
  status: string;
  created_at: string;
}

interface Sprint {
  id: string;
  name: string;
  path: string;
  timeFrame: string;
}

interface SprintWorkItem {
  id: string;
  title: string;
  type: string;
  state: string;
  story_points: number;
}

interface RetroReport {
  summary: string;
  what_went_well: string[];
  what_did_not_go_well: string[];
  average_sentiment: number;
  proposed_backlog_actions: any[];
}

// Preset Transcript Samples
const SAMPLES = [
  {
    title: "Sprint 4 Planning: Auth System & Staging Pipelines",
    transcript: `PM (Sarah): Welcome guys. Let's align on Sprint 4 backlog items. We need to finalize the secure oauth login module and integrate it. 
Dev (Dave): Yes, the login API is almost ready, but we need to support Auth0 token exchange and handle login failures with user-friendly warnings. Let's make that a user story.
PM (Sarah): Good. Let's budget 5 story points for that Auth0 story. Dave, we also need to build PostgreSQL database indices for search optimization on the users table.
Dev (Dave): That is a technical task, probably a 1 story point effort. I can execute it.
PM (Sarah): Great. What about local testing? We need to deploy our builds to the staging environment before publishing to production.
Dev (Dave): Yes, let's create a deployable staging pipeline configuration. A story called "As a developer, I want to deploy my branch to staging, so that I can verify integrations."
PM (Sarah): Excellent. Let's score that as 3 story points. I'll make sure it's set as high priority, priority 1. Let's get to work.`
  },
  {
    title: "Review Meeting: Stripe Billing Integration",
    transcript: `PM (Sarah): Alright, let's talk about subscription billing. We need to integrate Stripe payments.
Dev (Dave): We should support monthly and annual subscription plans. Also, the user should be able to download PDF invoices from their profile.
PM (Sarah): Let's split this. First piece: "As a customer, I want to pay using Card via Stripe, so that I can subscribe to services." This is a feature of high priority.
Dev (Dave): 8 story points for Stripe flow, it's quite complex. And invoice download can be a task under it, probably 2 story points.
PM (Sarah): Agreed. Let's add CORS exception fixes for local development too.
Dev (Dave): That's a task. 1 story point. Priority 2.`
  }
];

export default function App() {
  const [activeTab, setActiveTab] = useState<'meetings' | 'retro'>('meetings');
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const [backlogItems, setBacklogItems] = useState<BacklogItem[]>([]);
  
  // Create New Meeting Form
  const [newTitle, setNewTitle] = useState('');
  const [newProjectKey, setNewProjectKey] = useState('');
  const [newTranscript, setNewTranscript] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState(0);

  // Edit Modal State
  const [editingItem, setEditingItem] = useState<BacklogItem | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editPoints, setEditPoints] = useState(3);
  const [editPriority, setEditPriority] = useState(3);
  const [editTags, setEditTags] = useState('');

  // Azure DevOps Configurations
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [selectedSprint, setSelectedSprint] = useState<string>('');
  const [isPushing, setIsPushing] = useState(false);

  // Retro Page State
  const [sprintItems, setSprintItems] = useState<SprintWorkItem[]>([]);
  const [retroAnswers, setRetroAnswers] = useState({ q1: '', q2: '', q3: '', q4: '' });
  const [retroSentiment, setRetroSentiment] = useState(3);
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [isAggregatingRetro, setIsAggregatingRetro] = useState(false);
  const [retroReport, setRetroReport] = useState<RetroReport | null>(null);
  const [areActionsPushed, setAreActionsPushed] = useState(false);

  // Fetch initial list on load
  useEffect(() => {
    fetchMeetings();
    fetchSprints();
  }, []);

  useEffect(() => {
    if (selectedMeetingId) {
      fetchMeetingDetail(selectedMeetingId);
    }
  }, [selectedMeetingId]);

  useEffect(() => {
    if (selectedSprint) {
      fetchSprintItems();
      fetchExistingRetroReport();
    }
  }, [selectedSprint]);

  const fetchMeetings = async () => {
    try {
      const res = await fetch(`${API_URL}/api/meetings`);
      if (!res.ok) {
        console.error("Failed to fetch meetings:", res.statusText);
        return;
      }
      const data = await res.json();
      const meetingsData = Array.isArray(data) ? data : [];
      setMeetings(meetingsData);
      if (meetingsData.length > 0 && !selectedMeetingId) {
        setSelectedMeetingId(meetingsData[0].id);
      }
    } catch (e) {
      console.error("Error fetching meetings:", e);
    }
  };

  const fetchSprints = async () => {
    try {
      const res = await fetch(`${API_URL}/api/sprints`);
      if (!res.ok) {
        console.error("Failed to fetch sprints:", res.statusText);
        return;
      }
      const data = await res.json();
      const sprintsData = Array.isArray(data) ? data : [];
      setSprints(sprintsData);
      if (sprintsData.length > 0 && !selectedSprint) {
        setSelectedSprint(sprintsData[0].id);
      }
    } catch (e) {
      console.error("Error fetching sprints:", e);
    }
  };

  const fetchMeetingDetail = async (id: string) => {
    try {
      const res = await fetch(`${API_URL}/api/meetings/${id}`);
      if (!res.ok) {
        console.error("Failed to fetch meeting detail:", res.statusText);
        return;
      }
      const data = await res.json();
      setSelectedMeeting(data);
      setBacklogItems(Array.isArray(data.items) ? data.items : []);
    } catch (e) {
      console.error("Error fetching meeting detail:", e);
    }
  };

  const fetchSprintItems = async () => {
    const sprint = sprints.find(s => s.id === selectedSprint);
    if (!sprint) return;
    try {
      const res = await fetch(`${API_URL}/api/sprints/${sprint.id}/workitems?path=${encodeURIComponent(sprint.path)}`);
      if (!res.ok) {
        console.error("Failed to fetch sprint work items:", res.statusText);
        return;
      }
      const data = await res.json();
      setSprintItems(Array.isArray(data) ? data : []);
    } catch (e) {
      console.log("Error fetching sprint items:", e);
    }
  };

  const fetchExistingRetroReport = async () => {
    const sprint = sprints.find(s => s.id === selectedSprint);
    if (!sprint) return;
    try {
      setRetroReport(null);
      setAreActionsPushed(false);
      const res = await fetch(`${API_URL}/api/retro/${sprint.id}/report`);
      if (res.ok) {
        const data = await res.json();
        setRetroReport(data);
      }
    } catch (e) {
      console.log("Error fetching retro report:", e);
    }
  };

  // Triggering the LLM analysis chain
  const handleAnalyze = async () => {
    if (!newTitle.trim() || !newTranscript.trim()) {
      alert("Please provide both a meeting Title and Transcript content.");
      return;
    }
    setIsAnalyzing(true);
    setAnalysisStep(1);

    // Fake visual steps to match Ollama processing
    const timers = [
      setTimeout(() => setAnalysisStep(2), 2000),
      setTimeout(() => setAnalysisStep(3), 4000),
      setTimeout(() => setAnalysisStep(4), 6000),
    ];

    try {
      const res = await fetch(`${API_URL}/api/meetings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meetingTitle: newTitle, projectKey: newProjectKey, transcript: newTranscript })
      });
      const data = await res.json();
      
      timers.forEach(clearTimeout);
      setIsAnalyzing(false);
      
      // Reset inputs
      setNewTitle('');
      setNewProjectKey('');
      setNewTranscript('');
      
      // Refresh list & select the generated meeting
      await fetchMeetings();
      setSelectedMeetingId(data.id);
    } catch (e) {
      console.error(e);
      timers.forEach(clearTimeout);
      setIsAnalyzing(false);
      alert("Failed to connect to API backend or local LLM server.");
    }
  };

  // Trigger Item approval updates
  const handleToggleApprove = async (itemId: string, currentApproved: number) => {
    if (!selectedMeeting) return;
    
    // Optimistic UI state update
    const updatedItems = backlogItems.map(item => {
      if (item.id === itemId) {
        return { ...item, approved: currentApproved === 1 ? 0 : 1 };
      }
      return item;
    });
    setBacklogItems(updatedItems);
    
    try {
      const payloadItems = updatedItems.map(i => ({
        id: i.id,
        title: i.title,
        description: i.description,
        story_points: i.story_points,
        priority: i.priority,
        approved: i.approved === 1,
        tags: i.tags
      }));
      
      await fetch(`${API_URL}/api/meetings/${selectedMeeting.id}/items`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: payloadItems })
      });
      
      fetchMeetings();
    } catch (e) {
      console.error(e);
    }
  };

  // Open Edit Modal
  const startEditItem = (item: BacklogItem) => {
    setEditingItem(item);
    setEditTitle(item.title);
    setEditDescription(item.description);
    setEditPoints(item.story_points);
    setEditPriority(item.priority);
    setEditTags(item.tags.join(', '));
  };

  const saveEditedItem = async () => {
    if (!editingItem || !selectedMeeting) return;
    
    const tagArray = editTags.split(',').map(t => t.trim()).filter(t => t.length > 0);
    const updatedItems = backlogItems.map(item => {
      if (item.id === editingItem.id) {
        return {
          ...item,
          title: editTitle,
          description: editDescription,
          story_points: editPoints,
          priority: editPriority,
          tags: tagArray
        };
      }
      return item;
    });
    
    try {
      const payloadItems = updatedItems.map(i => ({
        id: i.id,
        title: i.title,
        description: i.description,
        story_points: i.story_points,
        priority: i.priority,
        approved: i.approved === 1,
        tags: i.tags
      }));
      
      const res = await fetch(`${API_URL}/api/meetings/${selectedMeeting.id}/items`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: payloadItems })
      });
      const data = await res.json();
      
      setBacklogItems(data.items || updatedItems);
      setEditingItem(null);
      fetchMeetings();
    } catch (e) {
      console.error(e);
      alert("Failed to update item.");
    }
  };

  // Pushing Approved Backlogs to Azure DevOps Boards
  const handlePushToAzure = async () => {
    if (!selectedMeeting) return;
    const targetSprint = sprints.find(s => s.id === selectedSprint);
    
    const approvedCount = backlogItems.filter(i => i.approved === 1 && !i.azure_id).length;
    if (approvedCount === 0) {
      alert("No approved, un-pushed backlog items in this meeting. Use the checklist to approve items first.");
      return;
    }
    
    setIsPushing(true);
    try {
      const res = await fetch(`${API_URL}/api/meetings/${selectedMeeting.id}/push-to-azure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ iteration_path: targetSprint?.path || null })
      });
      const data = await res.json();
      
      alert(`Success: ${data.pushed_count} work items pushed to Azure Boards!`);
      fetchMeetingDetail(selectedMeeting.id);
      fetchMeetings();
    } catch (e) {
      console.error(e);
      alert("Failed to push backlog items to Azure.");
    } finally {
      setIsPushing(false);
    }
  };

  // Submit employee retro feedback script
  const submitRetroFeedback = async () => {
    if (!selectedSprint) return;
    setIsSubmittingFeedback(true);
    try {
      const res = await fetch(`${API_URL}/api/retro/${selectedSprint}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: "developer-user",
          answers: retroAnswers,
          sentiment: retroSentiment
        })
      });
      
      if (res.ok) {
        alert("Stress Script retro questionnaire comments submitted successfully!");
        setRetroAnswers({ q1: '', q2: '', q3: '', q4: '' });
        setRetroSentiment(3);
      }
    } catch (e) {
      console.error(e);
      alert("Failed to submit feedback.");
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  // Generate sprint retro intelligence summary
  const generateRetroReport = async () => {
    const sprint = sprints.find(s => s.id === selectedSprint);
    if (!sprint) return;
    
    setIsAggregatingRetro(true);
    try {
      const res = await fetch(`${API_URL}/api/retro/${sprint.id}/aggregate?path=${encodeURIComponent(sprint.path)}`, {
        method: 'POST'
      });
      const data = await res.json();
      setRetroReport(data);
    } catch (e) {
      console.error(e);
      alert("Error building sprint retro summary.");
    } finally {
      setIsAggregatingRetro(false);
    }
  };

  // Push LLM proposed action items from Retro to Azure Boards
  const pushRetroActionsToAzure = async () => {
    const sprint = sprints.find(s => s.id === selectedSprint);
    if (!sprint || !retroReport) return;
    
    setIsPushing(true);
    try {
      const res = await fetch(`${API_URL}/api/retro/${sprint.id}/push-actions-to-azure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ iteration_path: sprint.path })
      });
      const data = await res.json();
      alert(`Success: ${data.pushed_count} retro action items created on Azure Boards!`);
      setAreActionsPushed(true);
      fetchSprintItems();
    } catch (e) {
      console.error(e);
      alert("Failed to sync retro action items.");
    } finally {
      setIsPushing(false);
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'pushed': return 'badge-pushed';
      case 'pending_push': return 'badge-pending';
      default: return 'badge-processed';
    }
  };

  // Helpers for Mock statistics calculations
  const totalPoints = sprintItems.reduce((acc, curr) => acc + (Number(curr.story_points) || 0), 0);
  const completedItems = sprintItems.filter(i => i.state === 'Closed' || i.state === 'Done');
  const completedCount = completedItems.length;
  const completionRate = sprintItems.length > 0 ? Math.round((completedCount / sprintItems.length) * 100) : 0;

  return (
    <div className="app-container">
      {/* Brand & Tabs Navigation */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">
            <svg fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/>
            </svg>
          </div>
          <h1 className="brand-title">DevOps<span>Intel</span></h1>
        </div>
        
        <nav className="nav-tabs">
          <button 
            className={`tab-btn ${activeTab === 'meetings' ? 'active' : ''}`}
            onClick={() => setActiveTab('meetings')}
          >
            Planning Backlog
          </button>
          <button 
            className={`tab-btn ${activeTab === 'retro' ? 'active' : ''}`}
            onClick={() => setActiveTab('retro')}
          >
            Sprint Retro Analytics
          </button>
        </nav>
      </header>

      {/* TABS INNER PAGES */}
      {activeTab === 'meetings' ? (
        <div className="dashboard-grid">
          
          {/* LEFT COLUMN: UPLOAD & MEETING SELECTION */}
          <aside className="left-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            
            {/* Upload Transcripts */}
            <div className="panel-card">
              <h3 className="panel-title">Ingest Transcript</h3>
              
              {/* Preset Shortcuts */}
              <div style={{ marginBottom: '1rem', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <span className="form-label" style={{ width: '100%' }}>Preset Demos:</span>
                {SAMPLES.map((s, idx) => (
                  <button 
                    key={idx} 
                    className="btn btn-secondary" 
                    style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                    onClick={() => {
                      setNewTitle(s.title);
                      setNewProjectKey('SampleProject');
                      setNewTranscript(s.transcript);
                    }}
                  >
                    Template {idx + 1}
                  </button>
                ))}
              </div>

              <div className="form-group">
                <label className="form-label">Meeting Name</label>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="Sprint 4 planning, etc." 
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Project Key</label>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="e.g., MyProject" 
                  value={newProjectKey}
                  onChange={(e) => setNewProjectKey(e.target.value)}
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Transcript Text</label>
                <textarea 
                  className="form-textarea" 
                  placeholder="Sarah (PM): Hi team, let's look at..." 
                  value={newTranscript}
                  onChange={(e) => setNewTranscript(e.target.value)}
                />
              </div>

              <button 
                className="btn btn-primary" 
                style={{ width: '100%' }}
                onClick={handleAnalyze}
                disabled={isAnalyzing}
              >
                {isAnalyzing ? "Processing LLM Pipeline..." : "Analyze Transcript"}
              </button>
            </div>

            {/* List of Meetings */}
            <div className="panel-card">
              <h3 className="panel-title">Processed Meetings</h3>
              <div className="meeting-list">
                {meetings.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center' }}>No meetings processed yet.</p>
                ) : (
                  meetings.map(m => (
                    <div 
                      key={m.id} 
                      className={`meeting-item-card ${selectedMeetingId === m.id ? 'active' : ''}`}
                      onClick={() => setSelectedMeetingId(m.id)}
                    >
                      <div className="meeting-info">
                        <span className="meeting-name">{m.title}</span>
                        <span className="meeting-date">{new Date(m.created_at).toLocaleDateString()}</span>
                      </div>
                      <span className={`badge ${getStatusBadgeClass(m.status)}`}>{m.status}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
            
          </aside>

          {/* RIGHT COLUMN: DETAILED BACKLOG AND DECISIONS */}
          <main className="main-panel">
            {isAnalyzing ? (
              <div className="panel-card loading-row">
                <div className="spinner"></div>
                <span className="loading-text">
                  {analysisStep === 1 && "Stage 1: Summarizing discussion contexts..."}
                  {analysisStep === 2 && "Stage 2: Extracting backlog feature tickets & user stories..."}
                  {analysisStep === 3 && "Stage 3: Story points effort & prioritization scoring..."}
                  {analysisStep === 4 && "Stage 4: Compliance checks to Agile framework ready cards..."}
                </span>
              </div>
            ) : selectedMeeting ? (
              <div className="summary-container">
                
                {/* Meeting Summarization Details */}
                <div className="meeting-summary-card">
                  <h2>{selectedMeeting.title}</h2>
                  <p>{selectedMeeting.summary || "No summary generated for this meeting."}</p>
                  
                  <div className="summary-split" style={{ marginTop: '1.25rem' }}>
                    <div className="bullet-card">
                      <h4>Key Decisions</h4>
                      {(selectedMeeting.decisions || []).length === 0 ? (
                        <p style={{ fontSize: '0.85rem' }}>No explicit decisions recorded.</p>
                      ) : (
                        <ul>
                          {(selectedMeeting.decisions || []).map((dec, i) => (
                            <li key={i}>{dec}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    
                    <div className="bullet-card">
                      <h4>Assumptions & Risks</h4>
                      {(selectedMeeting.risks || []).length === 0 ? (
                        <p style={{ fontSize: '0.85rem' }}>No risks resolved during discussion.</p>
                      ) : (
                        <ul>
                          {(selectedMeeting.risks || []).map((risk, i) => (
                            <li key={i}>{risk}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                </div>

                {/* Backlog Items List */}
                <div className="backlog-section">
                  <div className="backlog-toolbar">
                    <h3>Candidate Backlog Items ({backlogItems.length})</h3>
                    
                    <div className="sync-config">
                      <select 
                        className="form-select" 
                        style={{ width: 'auto', padding: '6px 10px' }}
                        value={selectedSprint}
                        onChange={(e) => setSelectedSprint(e.target.value)}
                      >
                        {sprints.map(s => (
                          <option key={s.id} value={s.id}>{s.name} ({s.timeFrame === 'current' ? 'Active' : s.timeFrame})</option>
                        ))}
                      </select>
                      
                      <button 
                        className="btn btn-primary"
                        onClick={handlePushToAzure}
                        disabled={isPushing}
                      >
                        {isPushing ? "Syncing..." : "Sync Approved to Azure Boards"}
                      </button>
                    </div>
                  </div>

                  <div className="backlog-grid">
                    {backlogItems.length === 0 ? (
                      <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>No backlog items generated for this meeting.</p>
                    ) : (
                      backlogItems.map(item => (
                        <div key={item.id} className="backlog-card">
                          <input 
                            type="checkbox" 
                            className="backlog-checkbox"
                            checked={item.approved === 1}
                            disabled={!!item.azure_id}
                            onChange={() => handleToggleApprove(item.id, item.approved)}
                          />
                          
                          <div className="backlog-card-body">
                            <div className="backlog-header-row">
                              <div className="backlog-title-area">
                                <span className={`type-indicator type-${item.type}`}>{item.type}</span>
                                <h4 className="backlog-title">{item.title}</h4>
                              </div>
                              {item.azure_id ? (
                                <div className="azure-badge">
                                  <svg fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
                                  </svg>
                                  Azure ID: {item.azure_id}
                                </div>
                              ) : (
                                <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '0.8rem' }} onClick={() => startEditItem(item)}>
                                  Edit Item
                                </button>
                              )}
                            </div>
                            
                            <p className="backlog-desc">{item.description}</p>
                            
                            {item.acceptance_criteria.length > 0 && (
                              <ul className="bullet-list">
                                {item.acceptance_criteria.map((ac, idx) => (
                                  <li key={idx}>{ac}</li>
                                ))}
                              </ul>
                            )}
                            
                            <div className="backlog-meta-footer">
                              <div className="meta-tags">
                                {item.tags.map((tag, idx) => (
                                  <span key={idx} className="meta-tag">{tag}</span>
                                ))}
                              </div>
                              <div className="meta-estimates">
                                <div className="meta-item">Points: <strong>{item.story_points || 'N/A'}</strong></div>
                                <div className="meta-item">Priority: <strong>{item.priority || 3}</strong></div>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>
            ) : (
              <div className="panel-card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
                <h3>Select a processed meeting or paste a transcript to begin analysis.</h3>
              </div>
            )}
          </main>

        </div>
      ) : (
        
        // RETRO intelligence TAB PAGE
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Sprint Settings Selector */}
          <div className="panel-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h2 style={{ fontSize: '1.25rem', marginBottom: '4px' }}>Sprint Retrospective Analyzer</h2>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>Sync real-time Azure sprint work items logs with individual sentiment reports.</p>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="form-label" style={{ marginBottom: 0 }}>Sprint Iteration:</span>
              <select 
                className="form-select" 
                style={{ width: '220px' }}
                value={selectedSprint}
                onChange={(e) => setSelectedSprint(e.target.value)}
              >
                {sprints.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.timeFrame === 'current' ? 'Active' : s.timeFrame})</option>
                ))}
              </select>
            </div>
          </div>

          {/* Sprint Backlog stats header widgets */}
          <div className="retro-stats-bar">
            <div className="stat-widget">
              <span className="stat-lbl">Sprint Closed tickets</span>
              <div className="stat-val">{completedCount} / {sprintItems.length}</div>
            </div>
            <div className="stat-widget">
              <span className="stat-lbl">Completion Rate</span>
              <div className="stat-val">{completionRate}%</div>
            </div>
            <div className="stat-widget">
              <span className="stat-lbl">Sprint Effort Points</span>
              <div className="stat-val">{totalPoints} SP</div>
            </div>
            <div className="stat-widget">
              <span className="stat-lbl">Azure Boards Link</span>
              <div className="stat-val" style={{ fontSize: '1rem', marginTop: '12px', color: 'var(--primary)', cursor: 'pointer' }}>Active Connect</div>
            </div>
          </div>

          {/* Retro Questionnaire & Summary Grid Layout */}
          <div className="retro-work-grid">
            
            {/* Stress Script survey comments inputs */}
            <div className="panel-card">
              <h3 className="panel-title">Stress Script Questionnaire</h3>
              
              <div className="stress-survey">
                <div className="form-group">
                  <label className="form-label">What went exceptionally well in this sprint?</label>
                  <textarea 
                    className="form-textarea" 
                    placeholder="We finished our features on time, team collaboration was great..." 
                    style={{ minHeight: '80px' }}
                    value={retroAnswers.q1}
                    onChange={(e) => setRetroAnswers({ ...retroAnswers, q1: e.target.value })}
                  />
                </div>
                
                <div className="form-group">
                  <label className="form-label">What blockers or friction did you experience?</label>
                  <textarea 
                    className="form-textarea" 
                    placeholder="Staging pipeline deployments were failing constantly, OAuth was tricky..." 
                    style={{ minHeight: '80px' }}
                    value={retroAnswers.q2}
                    onChange={(e) => setRetroAnswers({ ...retroAnswers, q2: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Did coding agents/tools support or delay work?</label>
                  <textarea 
                    className="form-textarea" 
                    placeholder="The copilot output boilerplate quickly but introduced test errors..." 
                    style={{ minHeight: '80px' }}
                    value={retroAnswers.q3}
                    onChange={(e) => setRetroAnswers({ ...retroAnswers, q3: e.target.value })}
                  />
                </div>
                
                <div className="form-group">
                  <label className="form-label">Active Sprint Sentiment (1-5)</label>
                  <div className="sentiment-selector">
                    <input 
                      type="range" 
                      min="1" 
                      max="5" 
                      className="sentiment-slider"
                      value={retroSentiment}
                      onChange={(e) => setRetroSentiment(Number(e.target.value))}
                    />
                    <div className="sentiment-display">
                      {retroSentiment === 1 && "😠 1.0"}
                      {retroSentiment === 2 && "😟 2.0"}
                      {retroSentiment === 3 && "😐 3.0"}
                      {retroSentiment === 4 && "🙂 4.0"}
                      {retroSentiment === 5 && "🚀 5.0"}
                    </div>
                  </div>
                </div>

                <button 
                  className="btn btn-secondary" 
                  style={{ width: '100%' }}
                  onClick={submitRetroFeedback}
                  disabled={isSubmittingFeedback}
                >
                  {isSubmittingFeedback ? "Submitting..." : "Submit Stress Questionnaire"}
                </button>
              </div>
            </div>

            {/* Generated retro report outputs */}
            <div className="panel-card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="panel-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Synthesized Retro Intelligence</span>
                <button 
                  className="btn btn-primary" 
                  style={{ padding: '6px 12px', fontSize: '0.85rem' }}
                  onClick={generateRetroReport}
                  disabled={isAggregatingRetro}
                >
                  {isAggregatingRetro ? "Synthesizing..." : "Generate Retro Report"}
                </button>
              </div>

              {isAggregatingRetro ? (
                <div className="loading-row">
                  <div className="spinner"></div>
                  <span className="loading-text">Combining boards backlog metrics with team sentiment replies...</span>
                </div>
              ) : retroReport ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', flex: 1 }}>
                  
                  {/* Summary */}
                  <div className="meeting-summary-card" style={{ margin: 0, padding: '16px' }}>
                    <div className="markdown-summary">
                      <h3>Sprint Summary</h3>
                      <p>{retroReport.summary}</p>
                      
                      <h3>What Went Well</h3>
                      <ul>
                        {retroReport.what_went_well?.map((item: string, i: number) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                      
                      <h3>Pain Points & Friction</h3>
                      <ul>
                        {retroReport.what_did_not_go_well?.map((item: string, i: number) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                      
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-subtle)', paddingTop: '10px', marginTop: '10.5px' }}>
                        <span className="form-label" style={{ marginBottom: 0 }}>Mean Team Sentiment:</span>
                        <span className="sentiment-display" style={{ fontSize: '1rem', padding: '1px 8px' }}>
                          {retroReport.average_sentiment ? `✨ ${retroReport.average_sentiment.toFixed(1)} / 5.0` : 'N/A'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions Proposed */}
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <h4 style={{ fontSize: '0.9rem', color: 'var(--text-main)', textTransform: 'uppercase' }}>Inferred Action Items</h4>
                      {retroReport.proposed_backlog_actions?.length > 0 && !areActionsPushed && (
                        <button 
                          className="btn btn-success" 
                          style={{ padding: '4px 10px', fontSize: '0.8rem' }}
                          onClick={pushRetroActionsToAzure}
                        >
                          Sync Actions to Azure Boards
                        </button>
                      )}
                      {areActionsPushed && (
                        <div className="azure-badge">
                          <svg fill="currentColor" viewBox="0 0 24 24">
                            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
                          </svg>
                          Synced Actions!
                        </div>
                      )}
                    </div>

                    <div className="retro-list">
                      {retroReport.proposed_backlog_actions?.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>No new actions proposed.</p>
                      ) : (
                        retroReport.proposed_backlog_actions?.map((act: any, idx: number) => (
                          <div key={idx} className="retro-list-item">
                            <div className="retro-list-item-header">
                              <span className="retro-list-item-title">{act.title}</span>
                              <span className="type-indicator type-task" style={{ fontSize: '0.65rem', padding: '1px 6px' }}>{act.type}</span>
                            </div>
                            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '4px' }}>{act.description}</p>
                            
                            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '6px', fontSize: '0.72rem', color: 'var(--text-tint)' }}>
                              <div>Points: <strong>{act.story_points || 'N/A'}</strong></div>
                              <div>Priority: <strong>{act.priority || 2}</strong></div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '6rem 2rem', color: 'var(--text-muted)', fontSize: '0.9rem', flex: 1, display: 'grid', placeItems: 'center' }}>
                  <p>Click "Generate Retro Report" above to trigger aggregate AI synthesis of boards metrics and surveys.</p>
                </div>
              )}
            </div>

          </div>

          {/* Active Sprint backlog tickets log */}
          <div className="panel-card">
            <h3 className="panel-title">Active Sprint Backlog Sync (Azure Boards)</h3>
            <div style={{ overflowX: 'auto' }}>
              {sprintItems.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', padding: '1rem 0' }}>No sprint tickets found or synced from Azure Boards.</p>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem', textHeading: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-tint)' }}>
                      <th style={{ padding: '8px' }}>ID</th>
                      <th style={{ padding: '8px' }}>Title</th>
                      <th style={{ padding: '8px' }}>Type</th>
                      <th style={{ padding: '8px' }}>State</th>
                      <th style={{ padding: '8px', textAlign: 'right' }}>Effort (SP)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sprintItems.map(item => (
                      <tr key={item.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '10px 8px', color: 'var(--text-tint)' }}>#{item.id}</td>
                        <td style={{ padding: '10px 8px', fontWeight: 500 }}>{item.title}</td>
                        <td style={{ padding: '10px 8px' }}>
                          <span className={`type-indicator type-${item.type.toLowerCase().includes('feature') ? 'feature' : item.type.toLowerCase().includes('task') ? 'task' : 'story'}`} style={{ fontSize: '0.68rem', padding: '2px 6px' }}>
                            {item.type}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px' }}>
                          <span className={`state-badge ${item.state === 'Closed' || item.state === 'Done' ? 'state-badge-closed' : 'state-badge-active'}`}>
                            {item.state}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>{item.story_points || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

        </div>
      )}

      {/* BACKLOG ITEM EDIT DETAIL MODAL OVERLAY */}
      {editingItem && (
        <div className="modal-overlay">
          <div className="modal-content">
            <header className="modal-header">
              <h3>Edit Backlog Candidate</h3>
              <button className="modal-close-btn" onClick={() => setEditingItem(null)}>&times;</button>
            </header>
            
            <div className="modal-body">
              <div className="form-group">
                <label className="form-label">Item Title</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Task Description</label>
                <textarea 
                  className="form-textarea" 
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Story Points (Effort)</label>
                  <select 
                    className="form-select" 
                    value={editPoints}
                    onChange={(e) => setEditPoints(Number(e.target.value))}
                  >
                    {[1, 2, 3, 5, 8, 13].map(pt => (
                      <option key={pt} value={pt}>{pt} SP</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Relative Priority</label>
                  <select 
                    className="form-select" 
                    value={editPriority}
                    onChange={(e) => setEditPriority(Number(e.target.value))}
                  >
                    {[1, 2, 3, 4].map(pr => (
                      <option key={pr} value={pr}>Priority {pr}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Scope Tags (Comma-separated)</label>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="frontend, database, api"
                  value={editTags}
                  onChange={(e) => setEditTags(e.target.value)}
                />
              </div>
            </div>
            
            <footer className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setEditingItem(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={saveEditedItem}>Save Modifications</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
