import { useState } from 'react';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';
import { createArtist } from '../../api';

export default function AddArtistModal({ initialName, onClose, onSuccess }) {
  const [name, setName] = useState(initialName);
  const [genre, setGenre] = useState('pop');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await createArtist({ name, genre });
      toast.success(`${name} added!`);
      onSuccess(res.data.slug);
    } catch (err) {
      if (err.response?.status === 409) {
        const existingSlug = err.response.data.slug;

        toast.success("Artist already exists! Redirecting...");

        if (existingSlug) {
          onSuccess(existingSlug);
        }
      } else {
        toast.error("Failed to add artist.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="bg-bg-card border border-border-col rounded-card p-8 w-full max-w-md">
        <h2 className="text-2xl font-bold text-text-primary mb-2">New Artist</h2>
        <p className="text-sm text-text-muted mb-6">Create a new node in the Knowledge Graph.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input required value={name} onChange={e => setName(e.target.value)} placeholder="Artist Name"
            className="w-full bg-bg-hover border border-border-col rounded-md px-4 py-2 text-text-primary" />

          <select value={genre} onChange={e => setGenre(e.target.value)}
            className="w-full bg-bg-hover border border-border-col rounded-md px-4 py-2 text-text-primary">
            {['pop','rap','rock','latin','r&b','edm'].map(g => <option key={g} value={g}>{g.toUpperCase()}</option>)}
          </select>

          <div className="flex gap-3 pt-4">
            <button type="button" onClick={onClose} className="flex-1 text-text-muted">Cancel</button>
            <button type="submit" disabled={loading} className="flex-1 py-2 bg-accent text-black rounded-pill font-bold">
              {loading ? "Saving..." : "Create Artist"}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
