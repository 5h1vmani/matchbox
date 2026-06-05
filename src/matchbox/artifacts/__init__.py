"""Artifact storage and retrieval for every generated output.

Covers: CV, cover letter, interview-prep brief, and follow-up /
thank-you / counter-offer drafts. Local-first; one SQLite DB per profile.
The table (``artifact``) is created by migration 007_sota.sql.
"""
