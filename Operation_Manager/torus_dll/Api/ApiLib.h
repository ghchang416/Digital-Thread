#pragma once

#ifdef INTELIGENTAPI_EXPORTS
#define INTELIGENT_API __declspec(dllexport)
#else
#define INTELIGENT_API __declspec(dllimport)
#endif
