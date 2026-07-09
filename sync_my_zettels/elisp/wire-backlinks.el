;;; wire-backlinks.el --- wire parent/child backlinks for assigned notes -*- lexical-binding: t; -*-

;; Driver invoked by sync_my_zettels/wire_backlinks.py under emacsclient.
;;
;; For each note PATH in the request JSON {"paths": [...]}, read the
;; folgezettel from its title, find the parent note (the node at the
;; parent address), and wire the pair using autoslip-roam's own helpers:
;;   - a parent backlink in the note (autoslip-roam--insert-backlink)
;;   - a forward child-link in the parent (autoslip-roam--insert-forward-link)
;; Both edits are deduplicated (skipped when the id link already exists) so
;; the phase is safe to re-run. Results are written to RESULT-FILE as JSON.
;;
;; Like the normalize driver, every note is processed headlessly: the
;; debugger is disabled and y/n prompts become caught errors, so an
;; unexpected confirmation can never freeze the daemon.

(require 'json)
(require 'cl-lib)

(defmacro smz-wb--headless (&rest body)
  "Run BODY so it can never block on input (see normalize-apply.el)."
  `(let ((debug-on-error nil)
         (debug-on-quit nil))
     (cl-letf (((symbol-function 'y-or-n-p)
                (lambda (prompt &rest _) (error "unexpected interactive prompt: %s" prompt)))
               ((symbol-function 'yes-or-no-p)
                (lambda (prompt &rest _) (error "unexpected interactive prompt: %s" prompt))))
       ,@body)))

(defun smz-wb--links-to-p (id)
  "Return non-nil if the current buffer already contains a link to ID."
  (save-excursion
    (goto-char (point-min))
    (search-forward (concat "id:" id) nil t)))

(defun smz-wb--file-links-to-p (file id)
  "Return non-nil if FILE already contains a link to ID."
  (and file (file-exists-p file)
       (with-temp-buffer
         (insert-file-contents file)
         (goto-char (point-min))
         (search-forward (concat "id:" id) nil t))))

(defun smz-wire-one (path)
  "Wire parent/child backlinks for the note at PATH based on its title address."
  (with-current-buffer (find-file-noselect path)
    (goto-char (point-min))
    (let* ((node (org-roam-node-at-point))
           (title (and node (org-roam-node-title node)))
           (addr (and title (autoslip-roam--extract-from-title title)))
           (parent-addr (and addr (autoslip-roam--parse-address addr)))
           (parent (and parent-addr (autoslip-roam--find-parent-node parent-addr))))
      (cond
       ((not node) (list (cons 'status "error") (cons 'message "no org-roam node at point")))
       ((not addr) (list (cons 'status "skipped") (cons 'message "no folgezettel in title")))
       ((not parent-addr)
        (list (cons 'status "skipped") (cons 'message "address is a root; no parent")))
       ((not parent)
        (list (cons 'status "skipped")
              (cons 'message (format "no parent note exists for %s" parent-addr))))
       (t
        (let* ((child-id (org-roam-node-id node))
               (parent-id (org-roam-node-id parent))
               (parent-file (org-roam-node-file parent))
               (back nil) (fwd nil))
          ;; Parent backlink in the child note (insert-backlink does not save).
          (unless (smz-wb--links-to-p parent-id)
            (autoslip-roam--insert-backlink parent)
            (save-buffer)
            (org-roam-db-update-file (buffer-file-name))
            (setq back t))
          ;; Forward child-link in the parent (insert-forward-link saves parent).
          (unless (smz-wb--file-links-to-p parent-file child-id)
            (autoslip-roam--insert-forward-link node parent-file)
            (setq fwd t))
          (list (cons 'status "wired")
                (cons 'parent (org-roam-node-title parent))
                (cons 'backlink back)
                (cons 'forward fwd))))))))

(defun smz-wire-backlinks (request-file result-file autoslip-path)
  "Wire backlinks for every note in REQUEST-FILE, writing RESULT-FILE.
Always writes a result file (results on success, {\"error\"} on a
top-level failure) so the Python caller never sees a silent no-op."
  (condition-case top-err
      (progn
        (load (expand-file-name autoslip-path) nil t)
        (require 'org-roam)
        (let* ((json-object-type 'alist)
               (json-array-type 'list)
               (json-key-type 'symbol)
               (request (json-read-file request-file))
               (paths (alist-get 'paths request))
               (results '()))
          (dolist (p paths)
            (push (append (list (cons 'path p))
                          (condition-case err
                              (smz-wb--headless (smz-wire-one p))
                            (error (list (cons 'status "error")
                                         (cons 'message (format "%s" err))))))
                  results))
          (with-temp-file result-file
            (insert (json-encode (list (cons 'results (nreverse results))))))
          t))
    (error
     (ignore-errors
       (with-temp-file result-file
         (insert (json-encode (list (cons 'error (format "%s" top-err)))))))
     nil)))

(provide 'wire-backlinks)
;;; wire-backlinks.el ends here
