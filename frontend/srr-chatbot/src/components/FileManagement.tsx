import React, { useState } from 'react';
import { FileText, Database, ArrowLeft, Search } from 'lucide-react';
import CaseFilesPanel from './CaseFilesPanel';
import KnowledgeBasePanel from './KnowledgeBasePanel';
import GradientButton from './GradientButton';
import './FileManagement.css';

type FileTab = 'case' | 'knowledge';

interface FileManagementProps {
  onSwitchToChat?: () => void;
}

const FileManagement: React.FC<FileManagementProps> = ({ onSwitchToChat }) => {
  const [activeTab, setActiveTab] = useState<FileTab>('case');
  const [searchQuery, setSearchQuery] = useState('');

  return (
    <div className="min-h-screen min-h-[100dvh] bg-background file-management-page">
      <div className="max-w-7xl mx-auto px-4 py-6 file-management-inner">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-6 file-management-header-row">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full gradient-red-yellow flex items-center justify-center">
                <FileText size={16} className="text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-foreground">File Management</h1>
                <p className="text-muted-foreground">Case files and knowledge base management</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {onSwitchToChat && (
                <GradientButton
                  onClick={onSwitchToChat}
                  size="sm"
                  variant="outline"
                  className="flex items-center gap-2"
                >
                  <ArrowLeft size={16} />
                  <span>Back to Chat</span>
                </GradientButton>
              )}
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 bg-muted rounded-lg p-1 animate-fade-in">
            <button
              className={`file-tab ${activeTab === 'case' ? 'active' : ''} flex-1 py-3 px-6 rounded-lg transition-all duration-300 flex items-center justify-center gap-2 font-medium text-sm`}
              onClick={() => setActiveTab('case')}
              style={{
                backgroundColor: activeTab === 'case' ? 'var(--card)' : 'transparent',
                boxShadow: activeTab === 'case' ? '0 2px 4px rgba(0, 0, 0, 0.08)' : 'none',
                color: activeTab === 'case' ? 'var(--foreground)' : 'var(--muted-foreground)',
              }}
            >
              <FileText size={16} />
              <span>Case Files</span>
            </button>
            <button
              className={`file-tab ${activeTab === 'knowledge' ? 'active' : ''} flex-1 py-3 px-6 rounded-lg transition-all duration-300 flex items-center justify-center gap-2 font-medium text-sm`}
              onClick={() => setActiveTab('knowledge')}
              style={{
                backgroundColor: activeTab === 'knowledge' ? 'var(--card)' : 'transparent',
                boxShadow: activeTab === 'knowledge' ? '0 2px 4px rgba(0, 0, 0, 0.08)' : 'none',
                color: activeTab === 'knowledge' ? 'var(--foreground)' : 'var(--muted-foreground)',
              }}
            >
              <Database size={16} />
              <span>Knowledge Base</span>
            </button>
          </div>
        </div>

        {/* Search - applies to active tab */}
        <div className="file-management-search mb-4">
          <div className="relative">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder={activeTab === 'case' ? 'Search case files (filename, case number, location, source...)' : 'Search knowledge base (filename, type...)'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-sm"
                aria-label="Clear search"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="file-management-content-wrapper">
          <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden animate-slide-in">
            {activeTab === 'case' ? (
              <CaseFilesPanel onSwitchToChat={onSwitchToChat} searchQuery={searchQuery} />
            ) : (
              <KnowledgeBasePanel searchQuery={searchQuery} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FileManagement;
