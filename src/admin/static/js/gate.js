/* Lets one action run at a time (cancel, pause/resume, EOD).
 *
 * Without it, a second action started while the first is still loading could open the
 * same confirm dialog and be confirmed by a single click on text the person never saw.
 */

export function createGate() {
  let busy = false;
  return {
    get busy() {
      return busy;
    },
    /** Runs `action` unless another one is running. Resolves true if it ran, false if refused. */
    async run(action) {
      if (busy) return false;
      busy = true;
      try {
        await action();
        return true;
      } finally {
        busy = false;
      }
    },
  };
}
