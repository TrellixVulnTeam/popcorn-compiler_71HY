.section .text.__set_thread_area, "ax"
.global __set_thread_area
.type   __set_thread_area,@function
.align 4
__set_thread_area:
	msr tpidr_el0,x0
	mov w0,#0
	ret
