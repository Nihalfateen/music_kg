import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
// Import the helper function we created
import { createSongsBulk } from '../../api'

export default function AddSongsModal({ artist, onClose, onSuccess }) {
  const [rows, setRows] = useState([{ name: '', album: '' }])
  const [loading, setLoading] = useState(false)

  const addRow = () => setRows([...rows, { name: '', album: '' }])
  const updateRow = (i, field, val) => {
    const newRows = [...rows];
    newRows[i][field] = val;
    setRows(newRows);
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    console.log("Submit triggered!", rows)

    const validSongs = rows.filter(r => r.name.trim() !== '' && r.album.trim() !== '');

    if (validSongs.length < rows.length) {
        toast.error("Please provide both a song name and an album for each entry.");
        return;
    }

    setLoading(true)
    try {
      await createSongsBulk({
        artist_slug: artist.slug,
        songs: validSongs
      })

      toast.success(`Successfully updated ${artist.name}'s library!`)
      onSuccess()
    } catch (err) {
      console.error("Submission error:", err)
      toast.error("Error updating GraphDB")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/90 backdrop-blur-md">
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        className="bg-bg-card border border-border-col rounded-card w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden">

        <div className="p-6 border-b border-border-col flex justify-between items-center">
          <h2 className="text-xl font-bold">Add Songs to {artist.name}</h2>
          <button onClick={onClose} className="text-2xl text-text-muted hover:text-text-primary">×</button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {rows.map((row, i) => (
              <div key={i} className="flex gap-3 items-end group">
                <div className="flex-1">
                  {i === 0 && <label className="text-[10px] uppercase font-bold text-text-muted mb-1 block">Song Title</label>}
                  <input required value={row.name} onChange={e => updateRow(i, 'name', e.target.value)}
                    className="w-full bg-bg-hover border border-border-col rounded-md px-3 py-2 text-sm focus:border-accent outline-none" placeholder="e.g. Anti-Hero" />
                </div>
                <div className="flex-1">
                  {i === 0 && <label className="text-[10px] uppercase font-bold text-text-muted mb-1 block">Album Name</label>}
                  <input required value={row.album} onChange={e => updateRow(i, 'album', e.target.value)}
                    className="w-full bg-bg-hover border border-border-col rounded-md px-3 py-2 text-sm focus:border-accent outline-none" placeholder="e.g. Midnights" />
                </div>
              </div>
            ))}

            <button type="button" onClick={addRow} className="w-full py-2 border-2 border-dashed border-border-col rounded-md text-text-muted hover:text-accent hover:border-accent transition-all text-sm font-bold">
              + Add Another Song
            </button>
          </div>

          <div className="p-6 border-t border-border-col flex gap-3 bg-bg-card">
            <button type="button" onClick={onClose} className="flex-1 font-bold text-text-muted hover:text-text-primary">
                Cancel
            </button>
            <button
                type="submit"
                disabled={loading}
                className="flex-[2] py-3 bg-accent text-black rounded-pill font-bold hover:bg-accent-hover disabled:opacity-50 transition-all shadow-lg shadow-accent/20"
            >
              {loading ? "Writing Triples..." : `Publish ${rows.filter(r => r.name).length} Songs`}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}
