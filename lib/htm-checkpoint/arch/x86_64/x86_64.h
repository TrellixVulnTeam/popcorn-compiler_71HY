#ifndef _HTM_X86_H
#define _HTM_X86_H

#ifndef __RTM__
# error "Cannot use x86/Intel-TSX extensions for this target or CPU"
#endif

#include <immintrin.h>

/*
 * Start transaction & convert TSX-NI's xbegin instruction status codes into a
 * generic format.
 *
 * BEGIN:
 *   _XBEGIN_STARTED - successfully started the transaction
 *
 * TRANSIENT:
 *   _XABORT_EXPLICIT - aborted by xabort instruction
 *   _XABORT_RETRY - hardware thinks transaction will succeed on retry
 *   _XABORT_DEBUG - aborted due to debug trap
 *   status == 0 - transaction aborted for other reason (i.e., page fault)
 *
 * CONFLICT:
 *   _XABORT_CONFLICT - memory cache line conflict detected
 *
 * CAPACITY:
 *   _XABORT_CAPACITY - hardware buffers reached capacity in transaction
 */
static inline transaction_status start_transaction()
{
  unsigned int code = _xbegin();

  if(code == _XBEGIN_STARTED) return BEGIN;
  else if((code & _XABORT_EXPLICIT) ||
          (code & _XABORT_RETRY) ||
          (code & _XABORT_DEBUG) ||
          !code) return TRANSIENT;
  else if(code & _XABORT_CONFLICT) return CONFLICT;
  else if(code & _XABORT_CAPACITY) return CAPACITY;

  return OTHER;
}

#define stop_transaction() _xend()
#define in_transaction() _xtest()

#endif /* _HTM_X86_H */

