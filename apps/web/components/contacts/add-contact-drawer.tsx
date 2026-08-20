"use client";

import { 
  Button, 
  Input, 
  Sheet, 
  SheetContent, 
  SheetDescription, 
  SheetFooter, 
  SheetHeader, 
  SheetTitle, 
  SheetTrigger 
} from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { Plus, UserPlus, Loader2 } from "lucide-react";

export function AddContactDrawer() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    phone: "",
    linkedin_url: "",
    company_id: "",
    role: "",
    source: "",
  });

  const { data: companies = [] } = useQuery({
    queryKey: ["companies", "add-contact"],
    queryFn: () => apiFetch<any[]>("/companies"),
  });

  const createContact = useMutation({
    mutationFn: () => apiFetch("/contacts", { 
      method: "POST", 
      body: JSON.stringify(form) 
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts"] });
      setOpen(false);
      setForm({
        full_name: "",
        email: "",
        phone: "",
        linkedin_url: "",
        company_id: "",
        role: "",
        source: "",
      });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createContact.mutate();
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="sm" className="h-8 gap-1.5 rounded-md bg-[#0A1128] px-3 text-xs font-semibold text-white hover:bg-[#1a2a53]">
          <Plus className="h-3.5 w-3.5" />
          Add Contact
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[400px] sm:w-[540px] border-l border-border/60">
        <SheetHeader className="border-b border-border/50 pb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 mb-2">
            <UserPlus className="h-5 w-5" />
          </div>
          <SheetTitle className="text-xl">Add New Contact</SheetTitle>
          <SheetDescription>
            Create a new primary or secondary contact for a company.
          </SheetDescription>
        </SheetHeader>

        <form onSubmit={handleSubmit} className="space-y-6 py-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Full Name</label>
              <Input 
                placeholder="Jane Doe" 
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Email</label>
                <Input 
                  type="email" 
                  placeholder="jane@example.com" 
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Phone</label>
                <Input 
                  placeholder="+91 99887 76655" 
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Company</label>
              <select 
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={form.company_id}
                onChange={(e) => setForm({ ...form, company_id: e.target.value })}
                required
              >
                <option value="">Select a company</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Role / Designation</label>
              <Input 
                placeholder="CTO / Founder" 
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Source</label>
              <select 
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={form.source}
                onChange={(e) => setForm({ ...form, source: e.target.value })}
              >
                <option value="">Select source</option>
                <option value="cold_call">Cold Call</option>
                <option value="referral">Referral</option>
                <option value="website">Website</option>
                <option value="linkedin">LinkedIn</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground">LinkedIn URL</label>
              <Input 
                placeholder="https://linkedin.com/in/jane-doe" 
                value={form.linkedin_url}
                onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })}
              />
            </div>
          </div>

          <SheetFooter className="border-t border-border/50 pt-6">
            <Button 
              type="button" 
              variant="outline" 
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button 
              type="submit" 
              className="bg-[#0A1128] text-white hover:bg-[#1a2a53]"
              disabled={createContact.isPending || !form.full_name || !form.company_id}
            >
              {createContact.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : "Create Contact"}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
