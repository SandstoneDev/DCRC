/* Optional test-run handoff, after all ordinary reports and file closes. MIT. */
#pragma once
int sa1_chain_set_next(const char *path);
int sa1_chain_set_restart(const char *base);
int sa1_chain_prepare(int code,const char *reason,int home,int modules_safe,const char *base);
void sa1_chain_launch(const volatile int *cancel);
