import React from 'react';
import {
  User, UserCircle, Cake, Phone, Fingerprint, CreditCard, Mail, Home,
  Briefcase, Coins, AlertTriangle, Cigarette, Stethoscope, Activity,
  Heart, Users, MapPin, Building2, Building, Landmark, Hash, Shield,
  FileText, Calendar, Pill, Wallet, UserPlus, Users2, FileSignature,
  // fallback
  Circle,
} from 'lucide-react';

const ICON_MAP = {
  'user':           User,
  'user-circle':    UserCircle,
  'cake':           Cake,
  'phone':          Phone,
  'fingerprint':    Fingerprint,
  'credit-card':    CreditCard,
  'mail':           Mail,
  'home':           Home,
  'briefcase':      Briefcase,
  'coins':          Coins,
  'alert-triangle': AlertTriangle,
  'cigarette':      Cigarette,
  'stethoscope':    Stethoscope,
  'activity':       Activity,
  'heart':          Heart,
  'users':          Users,
  'map-pin':        MapPin,
  'building-2':     Building2,
  'building':       Building,
  'landmark':       Landmark,
  'hash':           Hash,
  'shield':         Shield,
  'file-text':      FileText,
  'calendar':       Calendar,
  'pill':           Pill,
  'wallet':         Wallet,
  'user-plus':      UserPlus,
  'users-2':        Users2,
  'file-signature': FileSignature,
};

export default function FieldIcon({ name, size = 16, className = '' }) {
  const Comp = ICON_MAP[name] || Circle;
  return <Comp size={size} className={className} />;
}