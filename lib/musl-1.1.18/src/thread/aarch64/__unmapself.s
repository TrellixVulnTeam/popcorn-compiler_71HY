.section .text.__unmapself, "ax"
.global __unmapself
.type   __unmapself,%function
.align 4
__unmapself:
	mov x8,#215 // SYS_munmap
	svc 0
	mov x8,#93 // SYS_exit
	svc 0
