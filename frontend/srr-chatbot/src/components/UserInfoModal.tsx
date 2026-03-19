import React from 'react';
import { X, User, Building, Phone, Mail, Shield, LogOut } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import './UserInfoModal.css';

interface UserInfoModalProps {
  open: boolean;
  onClose: () => void;
}

const UserInfoModal: React.FC<UserInfoModalProps> = ({ open, onClose }) => {
  const { user, logout } = useAuth();

  if (!open || !user) return null;

  const handleLogout = () => {
    onClose();
    logout();
  };

  return (
    <>
      <div className="user-info-modal-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="user-info-modal" role="dialog" aria-labelledby="user-info-title">
        <div className="user-info-modal-header">
          <h2 id="user-info-title" className="user-info-modal-title">User info</h2>
          <button
            type="button"
            className="user-info-modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>
        <div className="user-info-modal-body">
          <div className="user-info-avatar-wrap">
            <div className="user-info-avatar">
              {(user.full_name && user.full_name.charAt(0)) || (user.email && user.email.charAt(0)) || '?'}
            </div>
          </div>
          <div className="user-info-rows">
            <div className="user-info-row">
              <User size={18} className="user-info-row-icon" />
              <span className="user-info-row-label">Name</span>
              <span className="user-info-row-value">{user.full_name || '—'}</span>
            </div>
            <div className="user-info-row">
              <Building size={18} className="user-info-row-icon" />
              <span className="user-info-row-label">Department</span>
              <span className="user-info-row-value">{user.department || '—'}</span>
            </div>
            <div className="user-info-row">
              <Phone size={18} className="user-info-row-icon" />
              <span className="user-info-row-label">Phone</span>
              <span className="user-info-row-value">{user.phone_number || '—'}</span>
            </div>
            <div className="user-info-row">
              <Mail size={18} className="user-info-row-icon" />
              <span className="user-info-row-label">Email</span>
              <span className="user-info-row-value">{user.email || '—'}</span>
            </div>
            <div className="user-info-row">
              <Shield size={18} className="user-info-row-icon" />
              <span className="user-info-row-label">Role</span>
              <span className="user-info-row-value">{user.role || '—'}</span>
            </div>
          </div>
        </div>
        <div className="user-info-modal-footer">
          <button type="button" className="user-info-logout-btn" onClick={handleLogout}>
            <LogOut size={20} />
            <span>Log out</span>
          </button>
        </div>
      </div>
    </>
  );
};

export default UserInfoModal;
