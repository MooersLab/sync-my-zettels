;;; normalize-apply.el --- apply a sync-my-zettels normalize plan -*- lexical-binding: t; -*-

;; Driver invoked by sync_my_zettels/normalize.py under emacsclient.
;;
;; Reads a request JSON of the form
;;   {"groups": [{"root_path": "...", "old_address": "1.9",
;;                "new_address": "1.14", "mode": "subtree"|"single",
;;                "leaves": ["1.9a", ...]}, ...]}
;; and, for each group, opens the root note, confirms its *current*
;; folgezettel still equals the planned old_address (a guard against the
;; vault having moved since the plan was previewed), then delegates to
;; autoslip-roam's own reparent commands.  Results are written to
;; RESULT-FILE as JSON so the Python side never has to parse elisp.
;;
;; Nothing here invents rename semantics: the actual title/filename/link
;; rewriting is entirely autoslip-roam-reparent[-subtree].

(require 'json)
(require 'cl-lib)

(defun smz-normalize-apply (request-file result-file autoslip-path)
  "Apply the normalize plan in REQUEST-FILE, writing results to RESULT-FILE.
AUTOSLIP-PATH is loaded to make the autoslip-roam commands available.

A result file is ALWAYS written: on success it holds {\"results\": [...]},
on a top-level failure it holds {\"error\": \"...\"}, so the Python caller
never has to distinguish a crash from a silent no-op."
  (condition-case top-err
      (smz-normalize-apply-1 request-file result-file autoslip-path)
    (error
     (ignore-errors
       (with-temp-file result-file
         (insert (json-encode (list (cons 'error (format "%s" top-err)))))))
     nil)))

(defun smz-normalize-apply-1 (request-file result-file autoslip-path)
  "Inner worker for `smz-normalize-apply'; may raise."
  (load (expand-file-name autoslip-path) nil t)
  (require 'org-roam)
  ;; Do NOT force `org-roam-db-sync' here: on this daemon it churns the
  ;; sqlite connection (a "sqlitep nil" finalizer error) and then leaves
  ;; `org-roam-node-at-point' unable to resolve. The live daemon DB is kept
  ;; current by normal use, and `autoslip-roam-reparent[-subtree]' calls
  ;; `autoslip-roam--maybe-sync-db' itself before mutating.
  (let* ((json-object-type 'alist)
         (json-array-type 'list)
         (json-key-type 'symbol)
         (request (json-read-file request-file))
         (groups (alist-get 'groups request))
         (results '()))
    (dolist (g groups)
      (let* ((root-path (alist-get 'root_path g))
             (old-address (alist-get 'old_address g))
             (new-address (alist-get 'new_address g))
             (mode (alist-get 'mode g))
             (res
              (condition-case err
                  (with-current-buffer (find-file-noselect root-path)
                    (goto-char (point-min))
                    (let* ((node (org-roam-node-at-point))
                           (title (and node (org-roam-node-title node)))
                           (cur (and title
                                     (autoslip-roam--extract-from-title title))))
                      (cond
                       ((not node)
                        (list (cons 'status "error")
                              (cons 'message "no org-roam node at point")))
                       ((not cur)
                        (list (cons 'status "error")
                              (cons 'message "note title carries no folgezettel")))
                       ((not (string= cur old-address))
                        (list (cons 'status "skipped")
                              (cons 'message
                                    (format "current address %s != planned %s"
                                            cur old-address))))
                       ((string= mode "subtree")
                        (let ((n (length (autoslip-roam--descendants-of cur))))
                          (autoslip-roam-reparent-subtree new-address)
                          (list (cons 'status "applied")
                                (cons 'descendants n))))
                       (t
                        (autoslip-roam-reparent new-address)
                        (list (cons 'status "applied")
                              (cons 'descendants 0))))))
                (error (list (cons 'status "error")
                             (cons 'message (format "%s" err)))))))
        (push (append (list (cons 'root_path root-path)
                            (cons 'old_address old-address)
                            (cons 'new_address new-address))
                      res)
              results)))
    ;; No global `save-some-buffers': autoslip-roam-reparent[-subtree] saves
    ;; every file it touches itself (via `save-buffer' +
    ;; `org-roam-db-update-file'), so we must never save unrelated buffers
    ;; that the user may have open with unsaved changes in this daemon.
    (with-temp-file result-file
      (insert (json-encode (list (cons 'results (nreverse results))))))
    t))

(provide 'normalize-apply)
;;; normalize-apply.el ends here
