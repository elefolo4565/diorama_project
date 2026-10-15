#include "FDTravelPoint.h"

#include "Components/ArrowComponent.h"

AFDTravelPoint::AFDTravelPoint()
{
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
#if WITH_EDITORONLY_DATA
	Arrow = CreateEditorOnlyDefaultSubobject<UArrowComponent>(TEXT("Arrow"));
	if (Arrow)
	{
		Arrow->SetupAttachment(RootComponent);
		Arrow->ArrowSize = 4.f;
		Arrow->ArrowColor = FColor(255, 160, 0);
	}
#endif
}
