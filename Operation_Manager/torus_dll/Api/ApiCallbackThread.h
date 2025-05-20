#pragma once


#if 1

typedef int (*callback_function)(int evt, int cmd, const char* command, char** result);
typedef unsigned int (__stdcall *callback_thread_function)(void* pvParam);

typedef struct _callback_thread_argv
{
	callback_function func;
	int evt;
	int cmd;
	unsigned char* command;
	int commandSize;
	char* result;
	int resSize;
}callback_thread_argv;

extern int g_guiLoaded;
extern int g_created_success;
extern int g_created_fail;

extern char* asynccommand;
extern char* asyncDataresult;
extern bool g_async_run;


unsigned int __stdcall BroadcastThread(void* pvParam);
unsigned int __stdcall ShowThread(void* pvParam);
unsigned int __stdcall CreateThread(void* pvParam);
unsigned int __stdcall ChangedLayoutThread(void* pvParam);
unsigned int __stdcall GetDataAsyncThread(void* pvParam);
unsigned int __stdcall RegistSubscribeDataThread(void* pvParam);
unsigned int __stdcall UnregistSubscribeDataThread(void* pvParam);
unsigned int __stdcall ClearSubscribeDataThread(void* pvParam);


#endif